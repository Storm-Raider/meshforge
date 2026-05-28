from __future__ import annotations
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QFrame, QSizePolicy, QToolTip, QCheckBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPainter, QColor

from meshforge.core.quality_engine import PASS_THRESHOLD, WARN_THRESHOLD
from meshforge.models.mesh_data import MeshData

_VTK_C3D4  = 10
_VTK_C3D10 = 24
_VTK_C3D8  = 12
_VTK_C3D6  = 13

_N_BINS = 20

_TOOLTIP_TEXT = (
    "Jacobian > 0.3: acceptable for structural FEA.\n"
    "Jacobian 0.1–0.3: borderline — review element location before submitting.\n"
    "Jacobian < 0.1: solver divergence risk in Abaqus implicit static."
)


class _HistogramWidget(QWidget):
    """Mini histogram of Jacobian distribution with pass/warn threshold markers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._counts = np.zeros(_N_BINS, dtype=np.int32)
        self.setFixedHeight(72)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_data(self, scalars: np.ndarray) -> None:
        if scalars is None or len(scalars) == 0:
            self._counts = np.zeros(_N_BINS, dtype=np.int32)
        else:
            counts, _ = np.histogram(scalars, bins=_N_BINS, range=(0.0, 1.0))
            self._counts = counts.astype(np.int32)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        w, h = self.width(), self.height()
        n = len(self._counts)
        max_count = max(int(self._counts.max()), 1)
        bar_w = w / n

        for i, count in enumerate(self._counts):
            bin_center = (i + 0.5) / n
            bar_h = int(h * count / max_count)
            x = int(i * bar_w)
            bw = max(int(bar_w) - 1, 1)
            # hue: 240° (blue) at 0 → 0° (red) at 1
            hue = int((1.0 - bin_center) * 240)
            painter.fillRect(x, h - bar_h, bw, bar_h, QColor.fromHsv(hue, 200, 210))

        # Warn threshold line (orange)
        x_warn = int(WARN_THRESHOLD * w)
        painter.setPen(QColor("#f0a500"))
        painter.drawLine(x_warn, 0, x_warn, h)

        # Pass threshold line (green)
        x_pass = int(PASS_THRESHOLD * w)
        painter.setPen(QColor("#4caf50"))
        painter.drawLine(x_pass, 0, x_pass, h)

        painter.end()


class QualityPanel(QWidget):
    """Right panel: quality dashboard + filter controls.

    Emits threshold_changed(lo, hi) when the user moves the filter slider.
    Main window connects this to the VTK lookup table update.
    """

    threshold_changed = pyqtSignal(float, float)
    isolate_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(220)
        self.setMaximumWidth(300)
        self._build_ui()
        self.set_empty()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ── Mesh statistics ───────────────────────────────────────────
        mesh_title = QLabel("Mesh")
        mesh_title.setStyleSheet("font-weight: bold; color: #aaa;")
        layout.addWidget(mesh_title)

        self._mesh_frame = QFrame()
        self._mesh_frame.setFrameShape(QFrame.Shape.StyledPanel)
        mesh_layout = QVBoxLayout(self._mesh_frame)
        mesh_layout.setContentsMargins(6, 6, 6, 6)
        mesh_layout.setSpacing(4)

        self._elem_label = self._stat_row(mesh_layout, "Elements", "#ccc")
        self._node_label = self._stat_row(mesh_layout, "Nodes", "#ccc")
        self._type_label = self._stat_row(mesh_layout, "Type", "#ccc")

        layout.addWidget(self._mesh_frame)

        # ── Quality ───────────────────────────────────────────────────
        qual_title = QLabel("Quality")
        qual_title.setStyleSheet("font-weight: bold; color: #aaa;")
        layout.addWidget(qual_title)

        # Stats grid
        self._stats_frame = QFrame()
        self._stats_frame.setFrameShape(QFrame.Shape.StyledPanel)
        stats_layout = QVBoxLayout(self._stats_frame)
        stats_layout.setContentsMargins(6, 6, 6, 6)
        stats_layout.setSpacing(4)

        self._pass_label = self._stat_row(stats_layout, "Pass (>0.3)", "#4caf50")
        self._warn_label = self._stat_row(stats_layout, "Warn (0.1–0.3)", "#f0a500")
        self._fail_label = self._stat_row(stats_layout, "Fail (<0.1)", "#e03c3c")

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        stats_layout.addWidget(divider)

        self._min_label = self._stat_row(stats_layout, "Min Jac", "#ccc")
        self._mean_label = self._stat_row(stats_layout, "Mean Jac", "#ccc")

        layout.addWidget(self._stats_frame)

        # Jacobian distribution histogram
        self._histogram = _HistogramWidget()
        layout.addWidget(self._histogram)

        # Filter slider — controls lo threshold for color display
        filter_header = QHBoxLayout()
        filter_title = QLabel("Filter threshold")
        filter_title.setToolTip(_TOOLTIP_TEXT)
        filter_title.setCursor(Qt.CursorShape.WhatsThisCursor)
        filter_header.addWidget(filter_title)
        filter_header.addStretch()
        self._threshold_value_label = QLabel("0.00")
        filter_header.addWidget(self._threshold_value_label)
        layout.addLayout(filter_header)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimum(0)
        self._slider.setMaximum(100)
        self._slider.setValue(0)
        self._slider.setToolTip(_TOOLTIP_TEXT)
        self._slider.valueChanged.connect(self._on_slider)
        layout.addWidget(self._slider)

        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel("0"))
        scale_row.addStretch()
        scale_row.addWidget(QLabel("1"))
        layout.addLayout(scale_row)

        # Isolate non-passing elements in the 3D viewport
        self._isolate_cb = QCheckBox("Isolate non-passing (Jac ≤ 0.3)")
        self._isolate_cb.setToolTip(
            "Show only elements with Jacobian ≤ 0.3 in the 3D view.\n"
            "Useful for locating buried failures inside solid geometry."
        )
        self._isolate_cb.setEnabled(False)
        self._isolate_cb.toggled.connect(self.isolate_changed)
        layout.addWidget(self._isolate_cb)

        layout.addStretch()

    def _stat_row(self, parent_layout, label_text: str, color: str) -> QLabel:
        row = QHBoxLayout()
        label = QLabel(label_text)
        label.setStyleSheet(f"color: {color};")
        label.setFont(QFont("Monospace", 9))
        value = QLabel("—")
        value.setFont(QFont("Monospace", 9))
        value.setAlignment(Qt.AlignmentFlag.AlignRight)
        row.addWidget(label)
        row.addStretch()
        row.addWidget(value)
        parent_layout.addLayout(row)
        return value

    def _on_slider(self, value: int) -> None:
        lo = value / 100.0
        self._threshold_value_label.setText(f"{lo:.2f}")
        self.threshold_changed.emit(lo, 1.0)

    def update_summary(self, summary: dict, mesh: MeshData | None = None) -> None:
        n = summary["element_count"]
        if n == 0:
            self.set_empty()
            return

        # Mesh stats
        if mesh is not None:
            self._elem_label.setText(f"{mesh.element_count:,}")
            self._node_label.setText(f"{mesh.node_count:,}")
            unique = set(np.unique(mesh.element_types).tolist())
            if unique == {_VTK_C3D10}:
                type_str = "Tet (C3D10)"
            elif unique == {_VTK_C3D8}:
                type_str = "Hex (C3D8)"
            elif unique == {_VTK_C3D4}:
                type_str = "Lin. Tet (C3D4)"
            else:
                type_str = "Mixed"
            self._type_label.setText(type_str)

        # Quality stats
        self._pass_label.setText(f"{summary['pass']:,}  ({summary['pass_pct']:.1f}%)")
        self._warn_label.setText(f"{summary['warn']:,}")
        self._fail_label.setText(f"{summary['fail']:,}")
        self._min_label.setText(f"{summary['min']:.3f}")
        self._mean_label.setText(f"{summary['mean']:.3f}")
        self._histogram.set_data(summary.get("scalars"))
        self._slider.setEnabled(True)
        self._isolate_cb.setEnabled(True)

    def set_empty(self) -> None:
        for lbl in (self._elem_label, self._node_label, self._type_label,
                    self._pass_label, self._warn_label, self._fail_label,
                    self._min_label, self._mean_label):
            lbl.setText("—")
        self._histogram.set_data(None)
        self._slider.setValue(0)
        self._slider.setEnabled(False)
        self._threshold_value_label.setText("0.00")
        self._isolate_cb.setChecked(False)
        self._isolate_cb.setEnabled(False)
