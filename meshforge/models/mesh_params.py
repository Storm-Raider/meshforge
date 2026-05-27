from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class RefinementZone:
    """One local mesh density zone tied to a surface or curve entity."""

    entity_type: str    # "surface" or "curve"
    entity_index: int   # 1-based index into Gmsh getEntities(2) or getEntities(1)
    size_factor: float  # 0.1–1.0 relative to global target size
    influence_radius: float  # model units (same as STEP file units)


@dataclass
class MeshParams:
    """All user-controllable meshing parameters.

    Passed from MeshPanel → MeshWorker → MeshEngine. None values mean
    "compute automatically from geometry".
    """

    # Global size multiplier applied to GeometryData.default_element_size()
    size_factor: float = 1.0

    # Absolute min/max characteristic length in model units.
    # None = auto: min = target * 0.5, max = target * 2.0
    min_size: float | None = None
    max_size: float | None = None

    # MeshSizeFromCurvature: segments per 2π. 0 = curvature refinement off.
    curvature_refinement: int = 0

    # Gmsh surface algorithm:  2=Automatic  5=Delaunay  6=Frontal-Delaunay
    surface_algorithm: int = 6

    # Gmsh volume algorithm:  1=Delaunay  9=HXT
    volume_algorithm: int = 1

    refinement_zones: list[RefinementZone] = field(default_factory=list)
