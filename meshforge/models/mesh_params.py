from __future__ import annotations
from dataclasses import dataclass, field


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
