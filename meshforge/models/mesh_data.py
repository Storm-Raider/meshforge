from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np


@dataclass
class MeshData:
    """Gmsh → VTK boundary. Produced by MeshEngine, consumed by QualityEngine and InpExporter."""

    nodes: np.ndarray           # (N, 3) float64 — node XYZ coordinates
    connectivity: np.ndarray    # (E, 10) int64  — C3D10 node indices (0-based)
    element_types: np.ndarray   # (E,) int32     — VTK element type per element (= 24 for C3D10)
    quality_scalars: np.ndarray = field(default_factory=lambda: np.empty(0))
    # (E,) float32 — scaled Jacobian per element; empty until QualityEngine runs

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def element_count(self) -> int:
        return len(self.connectivity)

    def has_quality(self) -> bool:
        return len(self.quality_scalars) == self.element_count
