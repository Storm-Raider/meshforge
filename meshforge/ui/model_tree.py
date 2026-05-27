from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QLabel
from PyQt6.QtCore import Qt

from meshforge.models.geometry_data import GeometryData
from meshforge.models.mesh_data import MeshData


class ModelTree(QWidget):
    """Left panel: model summary tree showing geometry and mesh statistics."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(200)
        self.setMaximumWidth(280)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        label = QLabel("Model")
        label.setStyleSheet("font-weight: bold; color: #aaa;")
        layout.addWidget(label)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(12)
        layout.addWidget(self._tree)

    def set_geometry(self, geo: GeometryData, filename: str) -> None:
        self._tree.clear()

        root = QTreeWidgetItem([filename])
        self._tree.addTopLevelItem(root)

        geom_item = QTreeWidgetItem(["Geometry"])
        geom_item.addChild(QTreeWidgetItem([f"Surfaces: {geo.surface_count}"]))
        geom_item.addChild(QTreeWidgetItem([f"BBox diagonal: {geo.bounding_box_diagonal:.2f}"]))
        geom_item.addChild(QTreeWidgetItem([f"Min edge: {geo.min_edge_length:.4f}"]))
        status_text = geo.healing_status.split(":")[0].upper()
        geom_item.addChild(QTreeWidgetItem([f"Healing: {status_text}"]))
        root.addChild(geom_item)
        root.setExpanded(True)
        geom_item.setExpanded(True)

    def set_mesh(self, mesh: MeshData) -> None:
        root = self._tree.topLevelItem(0)
        if root is None:
            return

        # Remove old mesh item if present
        for i in range(root.childCount()):
            if root.child(i).text(0) == "Mesh":
                root.removeChild(root.child(i))
                break

        mesh_item = QTreeWidgetItem(["Mesh"])
        mesh_item.addChild(QTreeWidgetItem([f"Nodes: {mesh.node_count:,}"]))
        mesh_item.addChild(QTreeWidgetItem([f"Elements: {mesh.element_count:,}"]))
        mesh_item.addChild(QTreeWidgetItem(["Type: C3D10"]))
        root.addChild(mesh_item)
        mesh_item.setExpanded(True)

    def set_quality(self, summary: dict) -> None:
        root = self._tree.topLevelItem(0)
        if root is None:
            return

        for i in range(root.childCount()):
            if root.child(i).text(0) == "Quality":
                root.removeChild(root.child(i))
                break

        q_item = QTreeWidgetItem(["Quality"])
        q_item.addChild(QTreeWidgetItem([f"Pass (>0.3): {summary['pass']:,}  ({summary['pass_pct']:.1f}%)"]))
        q_item.addChild(QTreeWidgetItem([f"Warn: {summary['warn']:,}"]))
        q_item.addChild(QTreeWidgetItem([f"Fail (<0.1): {summary['fail']:,}"]))
        q_item.addChild(QTreeWidgetItem([f"Min Jac: {summary['min']:.3f}"]))
        q_item.addChild(QTreeWidgetItem([f"Mean Jac: {summary['mean']:.3f}"]))
        root.addChild(q_item)
        q_item.setExpanded(True)

    def set_mesh_empty(self) -> None:
        """Remove the Mesh and Quality subtrees without clearing geometry."""
        root = self._tree.topLevelItem(0)
        if root is None:
            return
        for label in ("Mesh", "Quality"):
            for i in range(root.childCount()):
                if root.child(i).text(0) == label:
                    root.removeChild(root.child(i))
                    break

    def clear(self) -> None:
        self._tree.clear()
