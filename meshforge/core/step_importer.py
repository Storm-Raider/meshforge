from __future__ import annotations
import math
from pathlib import Path

from OCC.Core.BRep import BRep_Builder
from OCC.Core.BRepBndLib import brepbndlib
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Sewing
from OCC.Core.BRepCheck import BRepCheck_Analyzer
from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRep import BRep_Tool
from OCC.Core.ShapeFix import ShapeFix_Shape
from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.TopAbs import TopAbs_EDGE
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopoDS import TopoDS_Shape
from OCC.Core.IFSelect import IFSelect_RetDone

from meshforge.models.geometry_data import GeometryData


_SUPPORTED_EXTENSIONS = {".step", ".stp"}


class StepImporter:
    """Imports a STEP file, runs OCC healing, and returns GeometryData.

    No Qt imports. Instantiate once per import operation.
    """

    def import_file(self, path: str | Path) -> GeometryData:
        path = Path(path)
        self._validate_extension(path)
        shape = self._read_step(path)
        shape = self._heal(shape)
        healing_status = self._check(shape)
        surface_count = self._count_surfaces(shape)
        bbox_diagonal = self._bbox_diagonal(shape)
        min_edge = self._min_edge_length(shape)
        edge_count = self._count_edges(shape)
        return GeometryData(
            surface_count=surface_count,
            bounding_box_diagonal=bbox_diagonal,
            min_edge_length=min_edge,
            healing_status=healing_status,
            occ_shape=shape,
            edge_count=edge_count,
        )

    # ------------------------------------------------------------------
    # private helpers
    # ------------------------------------------------------------------

    def _validate_extension(self, path: Path) -> None:
        if path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported format: {path.suffix}. "
                "MeshForge v1 imports STEP files only (.step, .stp). "
                "Try exporting your geometry as STEP from your CAD system."
            )

    def _read_step(self, path: Path) -> TopoDS_Shape:
        reader = STEPControl_Reader()
        status = reader.ReadFile(str(path))
        if status != IFSelect_RetDone:
            raise RuntimeError(
                f"Failed to read STEP file: {path.name}. "
                "The file may contain unsupported geometry. "
                "Try exporting from your CAD tool as STEP AP214 or AP242."
            )
        reader.TransferRoots()
        return reader.OneShape()

    def _heal(self, shape: TopoDS_Shape) -> TopoDS_Shape:
        sewing = BRepBuilderAPI_Sewing(1e-6)
        sewing.Add(shape)
        sewing.Perform()
        sewn = sewing.SewedShape()

        fixer = ShapeFix_Shape(sewn)
        fixer.Perform()
        return fixer.Shape()

    def _check(self, shape: TopoDS_Shape) -> str:
        analyzer = BRepCheck_Analyzer(shape)
        if analyzer.IsValid():
            return "ok"

        # Count defects across all sub-shapes
        exp = TopExp_Explorer(shape, TopAbs_EDGE)
        defect_count = 0
        while exp.More():
            result = analyzer.Result(exp.Current())
            if result is not None and result.StatusOnShape(exp.Current()) != 0:
                defect_count += 1
            exp.Next()

        if defect_count == 0:
            defect_count = 1  # at least one defect triggered the failure

        return (
            f"failed:{defect_count} surface defects could not be repaired automatically. "
            "Try: (1) Re-export as STEP AP214 or AP242 with wider tolerances from your CAD system. "
            "(2) Check for non-manifold edges or degenerate faces in your CAD tool."
        )

    def _count_surfaces(self, shape: TopoDS_Shape) -> int:
        from OCC.Core.TopAbs import TopAbs_FACE
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        count = 0
        while exp.More():
            count += 1
            exp.Next()
        return count

    def _count_edges(self, shape: TopoDS_Shape) -> int:
        exp = TopExp_Explorer(shape, TopAbs_EDGE)
        count = 0
        while exp.More():
            count += 1
            exp.Next()
        return count

    def _bbox_diagonal(self, shape: TopoDS_Shape) -> float:
        box = Bnd_Box()
        brepbndlib.Add(shape, box)
        xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
        return math.sqrt((xmax - xmin) ** 2 + (ymax - ymin) ** 2 + (zmax - zmin) ** 2)

    def _min_edge_length(self, shape: TopoDS_Shape) -> float:
        """Walk all edges and return the shortest one. Falls back to 1% of bbox diagonal."""
        tool = BRep_Tool()
        exp = TopExp_Explorer(shape, TopAbs_EDGE)
        min_len = float("inf")

        while exp.More():
            edge = exp.Current()
            curve, u_start, u_end = tool.Curve(edge)
            if curve is not None:
                p_start = curve.Value(u_start)
                p_end = curve.Value(u_end)
                dx = p_end.X() - p_start.X()
                dy = p_end.Y() - p_start.Y()
                dz = p_end.Z() - p_start.Z()
                length = math.sqrt(dx * dx + dy * dy + dz * dz)
                if length > 1e-10:
                    min_len = min(min_len, length)
            exp.Next()

        if min_len == float("inf"):
            bbox = Bnd_Box()
            brepbndlib.Add(shape, bbox)
            xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
            diagonal = math.sqrt((xmax - xmin) ** 2 + (ymax - ymin) ** 2 + (zmax - zmin) ** 2)
            return diagonal * 0.01

        return min_len
