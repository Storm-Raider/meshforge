from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QDoubleSpinBox, QSpinBox, QComboBox, QPushButton,
    QCheckBox, QFrame, QGroupBox, QScrollArea,
)
from PyQt6.QtCore import Qt, pyqtSignal

from meshforge.models.mesh_params import MeshParams, RefinementZone

_SURFACE_ALGOS = [
    ("Frontal-Delaunay", 6),
    ("Delaunay", 5),
    ("Automatic", 2),
]

_VOLUME_ALGOS = [
    ("Delaunay", 1),
    ("HXT (fast)", 9),
]

_MESH_TYPES = [
    ("Tet (C3D10)", "tet"),
    ("Hex (C3D8)", "hex"),
]


class _ZoneRow(QWidget):
    """One refinement zone row: entity selector + size factor + radius + remove."""

    removed = pyqtSignal(object)

    def __init__(self, surface_count: int, edge_count: int, parent=None):
        super().__init__(parent)
        self._surface_count = max(1, surface_count)
        self._edge_count = max(1, edge_count)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(3)

        self._type_combo = QComboBox()
        self._type_combo.addItems(["Surface", "Edge"])
        self._type_combo.setFixedWidth(64)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)

        self._index_spin = QSpinBox()
        self._index_spin.setRange(1, self._surface_count)
        self._index_spin.setValue(1)
        self._index_spin.setFixedWidth(40)
        self._index_spin.setToolTip("Entity index (1-based)")

        self._factor_spin = QDoubleSpinBox()
        self._factor_spin.setRange(0.1, 1.0)
        self._factor_spin.setSingleStep(0.05)
        self._factor_spin.setDecimals(2)
        self._factor_spin.setValue(0.3)
        self._factor_spin.setFixedWidth(50)
        self._factor_spin.setToolTip("Local size factor relative to global (0.1 = 10%)")

        self._radius_spin = QDoubleSpinBox()
        self._radius_spin.setRange(0.001, 99999.0)
        self._radius_spin.setDecimals(2)
        self._radius_spin.setValue(5.0)
        self._radius_spin.setFixedWidth(56)
        self._radius_spin.setToolTip("Influence radius (STEP file units)")

        remove_btn = QPushButton("✕")
        remove_btn.setFixedSize(18, 18)
        remove_btn.setStyleSheet("font-size: 9px; padding: 0;")
        remove_btn.clicked.connect(lambda: self.removed.emit(self))

        layout.addWidget(self._type_combo)
        layout.addWidget(self._index_spin)
        layout.addWidget(self._factor_spin)
        layout.addWidget(self._radius_spin)
        layout.addWidget(remove_btn)

    def _on_type_changed(self, index: int) -> None:
        count = self._surface_count if index == 0 else self._edge_count
        current = min(self._index_spin.value(), count)
        self._index_spin.setRange(1, count)
        self._index_spin.setValue(current)

    def update_counts(self, surface_count: int, edge_count: int) -> None:
        self._surface_count = max(1, surface_count)
        self._edge_count = max(1, edge_count)
        self._on_type_changed(self._type_combo.currentIndex())

    def get_zone(self) -> RefinementZone:
        entity_type = "surface" if self._type_combo.currentIndex() == 0 else "curve"
        return RefinementZone(
            entity_type=entity_type,
            entity_index=self._index_spin.value(),
            size_factor=self._factor_spin.value(),
            influence_radius=self._radius_spin.value(),
        )


class MeshPanel(QWidget):
    """Left panel: mesh parameter controls + Re-mesh button.

    Call set_geometry(geo) when geometry loads to enable the panel and
    populate entity counts for refinement zone selectors.
    get_params() returns the current MeshParams at any time.
    """

    remesh_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(200)
        self.setMaximumWidth(300)
        self._target_size: float = 0.0
        self._surface_count: int = 1
        self._edge_count: int = 1
        self._zone_rows: list[_ZoneRow] = []
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
            refinement_zones=[row.get_zone() for row in self._zone_rows],
            mesh_type=_MESH_TYPES[self._mesh_type_combo.currentIndex()][1],
            smooth_iter=self._smooth_spin.value(),
        )

    def set_geometry_defaults(self, target_size: float) -> None:
        """Called after import so auto min/max labels reflect actual geometry."""
        self._target_size = target_size
        self._update_auto_labels()

    def set_geometry(self, geo) -> None:
        """Update entity counts for refinement zone dropdowns. Clears any existing zones."""
        from meshforge.models.geometry_data import GeometryData
        if not isinstance(geo, GeometryData):
            return
        for row in list(self._zone_rows):
            self._remove_zone(row)
        self._surface_count = max(1, geo.surface_count)
        self._edge_count = max(1, geo.edge_count)
        self._zones_count_label.setText(
            f"{geo.surface_count} surfaces, {geo.edge_count} edges"
        )
        self.set_geometry_defaults(geo.default_element_size())

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

        # Quick presets
        preset_row = QHBoxLayout()
        preset_row.setSpacing(4)
        for label, factor in (("Coarse", 2.0), ("Medium", 1.0), ("Fine", 0.5)):
            btn = QPushButton(label)
            btn.setFixedHeight(22)
            btn.setStyleSheet("font-size: 10px; padding: 0 4px;")
            btn.setToolTip(f"Size factor {factor}×")
            btn.clicked.connect(lambda _, f=factor: self._apply_preset(f))
            preset_row.addWidget(btn)
        layout.addLayout(preset_row)

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
        self._size_slider.setRange(1, 50)
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

        # Element type
        layout.addWidget(self._make_label("Element type"))
        self._mesh_type_combo = QComboBox()
        for name, _ in _MESH_TYPES:
            self._mesh_type_combo.addItem(name)
        self._mesh_type_combo.setToolTip(
            "Tet (C3D10): quadratic tetrahedra — robust, works on all geometry.\n"
            "Hex (C3D8): linear hexahedra via barycentric subdivision — ~4x element count."
        )
        layout.addWidget(self._mesh_type_combo)

        # Smoothing passes
        smooth_row = QHBoxLayout()
        smooth_row.addWidget(self._make_label("Smoothing passes"))
        self._smooth_spin = QSpinBox()
        self._smooth_spin.setRange(0, 10)
        self._smooth_spin.setValue(0)
        self._smooth_spin.setFixedWidth(58)
        self._smooth_spin.setToolTip(
            "Gmsh optimizer passes applied after volume meshing.\n"
            "0 = off. 3–5 recommended for tet meshes with poor-quality elements.\n"
            "Uses Laplacian + gradient descent — safe for both Tet and Hex."
        )
        smooth_row.addWidget(self._smooth_spin)
        layout.addLayout(smooth_row)

        # Refinement Zones
        zones_group = QGroupBox("Refinement Zones")
        zones_group.setStyleSheet(
            "QGroupBox { color: #aaa; font-size: 11px; font-weight: bold; "
            "border: 1px solid #444; border-radius: 3px; margin-top: 6px; padding-top: 4px; } "
            "QGroupBox::title { subcontrol-origin: margin; left: 6px; }"
        )
        zones_layout = QVBoxLayout(zones_group)
        zones_layout.setContentsMargins(4, 4, 4, 4)
        zones_layout.setSpacing(3)

        self._zones_count_label = QLabel("Load a STEP file to add zones")
        self._zones_count_label.setStyleSheet("color: #666; font-size: 10px;")
        zones_layout.addWidget(self._zones_count_label)

        # Column headers
        header_row = QHBoxLayout()
        header_row.setSpacing(3)
        for text, width in (("Type", 64), ("Idx", 40), ("Factor", 50), ("Radius", 56)):
            lbl = QLabel(text)
            lbl.setFixedWidth(width)
            lbl.setStyleSheet("color: #777; font-size: 9px;")
            header_row.addWidget(lbl)
        header_row.addStretch()
        zones_layout.addLayout(header_row)

        # Container for zone rows
        self._zones_container = QWidget()
        self._zones_layout = QVBoxLayout(self._zones_container)
        self._zones_layout.setContentsMargins(0, 0, 0, 0)
        self._zones_layout.setSpacing(2)

        scroll = QScrollArea()
        scroll.setWidget(self._zones_container)
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(120)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        zones_layout.addWidget(scroll)

        self._add_zone_btn = QPushButton("+ Add Zone")
        self._add_zone_btn.setFixedHeight(22)
        self._add_zone_btn.setStyleSheet("font-size: 10px; padding: 0 6px;")
        self._add_zone_btn.clicked.connect(self._add_zone)
        zones_layout.addWidget(self._add_zone_btn)

        layout.addWidget(zones_group)

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

    def _apply_preset(self, factor: float) -> None:
        self._size_spin.setValue(factor)

    def _add_zone(self) -> None:
        row = _ZoneRow(self._surface_count, self._edge_count, self._zones_container)
        row.removed.connect(self._remove_zone)
        self._zones_layout.addWidget(row)
        self._zone_rows.append(row)

    def _remove_zone(self, row: _ZoneRow) -> None:
        if row in self._zone_rows:
            self._zone_rows.remove(row)
        self._zones_layout.removeWidget(row)
        row.deleteLater()
