from __future__ import annotations
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QFrame, QSizePolicy, QToolTip, QCheckBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from meshforge.core.quality_engine import PASS_THRESHOLD, WARN_THRESHOLD

_TOOLTIP_TEXT = (
    "Jacobian > 0.3: acceptable for structural FEA.\n"
    "Jacobian 0.1–0.3: borderline — review element location before submitting.\n"
    "Jacobian < 0.1: solver divergence risk in Abaqus implicit static."
)


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

        title = QLabel("Quality")
        title.setStyleSheet("font-weight: bold; color: #aaa;")
        layout.addWidget(title)

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

    def update_summary(self, summary: dict) -> None:
        n = summary["element_count"]
        if n == 0:
            self.set_empty()
            return
        self._pass_label.setText(f"{summary['pass']:,}  ({summary['pass_pct']:.1f}%)")
        self._warn_label.setText(f"{summary['warn']:,}")
        self._fail_label.setText(f"{summary['fail']:,}")
        self._min_label.setText(f"{summary['min']:.3f}")
        self._mean_label.setText(f"{summary['mean']:.3f}")
        self._slider.setEnabled(True)
        self._isolate_cb.setEnabled(True)

    def set_empty(self) -> None:
        for lbl in (self._pass_label, self._warn_label, self._fail_label,
                    self._min_label, self._mean_label):
            lbl.setText("—")
        self._slider.setValue(0)
        self._slider.setEnabled(False)
        self._threshold_value_label.setText("0.00")
        self._isolate_cb.setChecked(False)
        self._isolate_cb.setEnabled(False)
