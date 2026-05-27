from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QDoubleSpinBox, QSpinBox, QComboBox, QPushButton,
    QCheckBox, QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal

from meshforge.models.mesh_params import MeshParams

_SURFACE_ALGOS = [
    ("Frontal-Delaunay", 6),
    ("Delaunay", 5),
    ("Automatic", 2),
]

_VOLUME_ALGOS = [
    ("Delaunay", 1),
    ("HXT (fast)", 9),
]


class MeshPanel(QWidget):
    """Left panel: mesh parameter controls + Re-mesh button.

    Call set_geometry_defaults(target_size) when geometry loads so the
    auto min/max labels show meaningful values. get_params() returns the
    current MeshParams at any time.
    """

    remesh_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(200)
        self.setMaximumWidth(280)
        self._target_size: float = 0.0
        self._build_ui()
        self.set_enabled(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_params(self) -> MeshParams:
        return MeshParams(
            size_factor=self._size_spin.value(),
            min_size=None if self._min_auto.isChecked() else self._min_spin.value(),
            max_size=None if self._max_auto.isChecked() else self._max_spin.value(),
            curvature_refinement=self._curvature_spin.value(),
            surface_algorithm=_SURFACE_ALGOS[self._surf_combo.currentIndex()][1],
            volume_algorithm=_VOLUME_ALGOS[self._vol_combo.currentIndex()][1],
        )

    def set_geometry_defaults(self, target_size: float) -> None:
        """Called after import so auto min/max labels reflect actual geometry."""
        self._target_size = target_size
        self._update_auto_labels()

    def set_enabled(self, enabled: bool) -> None:
        self._remesh_btn.setEnabled(enabled)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(6)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #444;")
        layout.addWidget(divider)

        title = QLabel("Mesh Settings")
        title.setStyleSheet("font-weight: bold; color: #aaa;")
        layout.addWidget(title)

        # Size factor
        layout.addWidget(self._make_label("Size factor"))
        sf_row = QHBoxLayout()
        self._size_spin = QDoubleSpinBox()
        self._size_spin.setRange(0.1, 5.0)
        self._size_spin.setSingleStep(0.1)
        self._size_spin.setDecimals(1)
        self._size_spin.setValue(1.0)
        self._size_spin.setFixedWidth(60)
        self._size_spin.valueChanged.connect(self._update_auto_labels)
        self._size_slider = QSlider(Qt.Orientation.Horizontal)
        self._size_slider.setRange(1, 50)   # 0.1–5.0 in steps of 0.1
        self._size_slider.setValue(10)
        self._size_slider.valueChanged.connect(self._on_slider)
        self._size_spin.valueChanged.connect(self._on_spinbox)
        sf_row.addWidget(self._size_spin)
        sf_row.addWidget(self._size_slider)
        layout.addLayout(sf_row)

        self._target_label = QLabel("Target: —")
        self._target_label.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(self._target_label)

        # Min element size
        layout.addWidget(self._make_label("Min element size"))
        min_row = QHBoxLayout()
        self._min_auto = QCheckBox("Auto")
        self._min_auto.setChecked(True)
        self._min_auto.toggled.connect(self._on_min_auto)
        self._min_spin = QDoubleSpinBox()
        self._min_spin.setRange(0.001, 9999.0)
        self._min_spin.setDecimals(3)
        self._min_spin.setEnabled(False)
        min_row.addWidget(self._min_auto)
        min_row.addWidget(self._min_spin)
        layout.addLayout(min_row)

        # Max element size
        layout.addWidget(self._make_label("Max element size"))
        max_row = QHBoxLayout()
        self._max_auto = QCheckBox("Auto")
        self._max_auto.setChecked(True)
        self._max_auto.toggled.connect(self._on_max_auto)
        self._max_spin = QDoubleSpinBox()
        self._max_spin.setRange(0.001, 99999.0)
        self._max_spin.setDecimals(3)
        self._max_spin.setEnabled(False)
        max_row.addWidget(self._max_auto)
        max_row.addWidget(self._max_spin)
        layout.addLayout(max_row)

        # Curvature refinement
        curv_row = QHBoxLayout()
        curv_row.addWidget(self._make_label("Curvature segs/2π"))
        self._curvature_spin = QSpinBox()
        self._curvature_spin.setRange(0, 50)
        self._curvature_spin.setValue(0)
        self._curvature_spin.setToolTip("Segments per full circle for curved surface refinement.\n0 = disabled.")
        self._curvature_spin.setFixedWidth(58)
        curv_row.addWidget(self._curvature_spin)
        layout.addLayout(curv_row)

        # Surface algorithm
        layout.addWidget(self._make_label("Surface algorithm"))
        self._surf_combo = QComboBox()
        for name, _ in _SURFACE_ALGOS:
            self._surf_combo.addItem(name)
        layout.addWidget(self._surf_combo)

        # Volume algorithm
        layout.addWidget(self._make_label("Volume algorithm"))
        self._vol_combo = QComboBox()
        for name, _ in _VOLUME_ALGOS:
            self._vol_combo.addItem(name)
        self._vol_combo.setToolTip(
            "Delaunay: robust, recommended for most geometry.\n"
            "HXT: faster on large models but may fail on multi-body assemblies."
        )
        layout.addWidget(self._vol_combo)

        # Re-mesh button
        self._remesh_btn = QPushButton("Re-mesh")
        self._remesh_btn.clicked.connect(self.remesh_requested)
        layout.addWidget(self._remesh_btn)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #bbb; font-size: 11px;")
        return lbl

    def _on_slider(self, value: int) -> None:
        self._size_spin.blockSignals(True)
        self._size_spin.setValue(value / 10.0)
        self._size_spin.blockSignals(False)
        self._update_auto_labels()

    def _on_spinbox(self, value: float) -> None:
        self._size_slider.blockSignals(True)
        self._size_slider.setValue(round(value * 10))
        self._size_slider.blockSignals(False)
        self._update_auto_labels()

    def _update_auto_labels(self) -> None:
        if self._target_size <= 0:
            self._target_label.setText("Target: —")
            return
        target = self._target_size * self._size_spin.value()
        self._target_label.setText(f"Target: {target:.3g} mm")
        if self._min_auto.isChecked():
            self._min_spin.setValue(target * 0.5)
        if self._max_auto.isChecked():
            self._max_spin.setValue(target * 2.0)

    def _on_min_auto(self, checked: bool) -> None:
        self._min_spin.setEnabled(not checked)
        if checked:
            self._update_auto_labels()

    def _on_max_auto(self, checked: bool) -> None:
        self._max_spin.setEnabled(not checked)
        if checked:
            self._update_auto_labels()
