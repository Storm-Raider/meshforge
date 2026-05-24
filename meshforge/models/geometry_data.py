from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from OCC.Core.TopoDS import TopoDS_Shape


@dataclass
class GeometryData:
    """OCC → Gmsh boundary. Produced by StepImporter, consumed by MeshEngine."""

    surface_count: int
    bounding_box_diagonal: float
    min_edge_length: float
    healing_status: str          # "ok" | "warn:<detail>" | "failed:<detail>"
    occ_shape: "TopoDS_Shape"

    def is_valid(self) -> bool:
        return self.healing_status.startswith("ok") or self.healing_status.startswith("warn")

    def default_element_size(self) -> float:
        """MeshForge default: min(3% bbox diagonal, 0.5 × min edge length)."""
        return min(0.03 * self.bounding_box_diagonal, 0.5 * self.min_edge_length)
