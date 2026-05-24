from __future__ import annotations
import re
import threading
import numpy as np

import gmsh

from meshforge.models.geometry_data import GeometryData
from meshforge.models.mesh_data import MeshData

# VTK element type for 10-node quadratic tetrahedron (C3D10)
VTK_QUADRATIC_TETRA = 24

# Surface meshing: Frontal-Delaunay (locked choice from design doc)
_SURFACE_ALGO = 6

# Volume meshing: HXT (Algorithm3D=9) — confirmed winner from Week 0 benchmark.
# Update to 1 (Delaunay) if production geometry shows HXT failures.
_VOLUME_ALGO = 9

_GMSH_LOCK = threading.Lock()


class MeshEngine:
    """Generates a C3D10 tet mesh from a GeometryData OCC shape via Gmsh.

    No Qt imports. One active instance per process (Gmsh global state).
    The caller (MeshWorker) is responsible for checking cancel_requested
    after this returns, and discarding the result if set.
    """

    def __init__(self, size_factor: float = 1.0):
        self._size_factor = size_factor  # multiplier on the default element size

    def mesh(self, geo: GeometryData) -> MeshData:
        """Run full surface + volume mesh. Returns MeshData with no quality_scalars."""
        with _GMSH_LOCK:
            return self._mesh_locked(geo)

    def _mesh_locked(self, geo: GeometryData) -> MeshData:
        gmsh.initialize()
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("General.Verbosity", 1)
        gmsh.model.add("meshforge")

        try:
            self._load_shape(geo)
            self._set_options(geo)
            gmsh.model.mesh.generate(3)
            gmsh.model.mesh.setOrder(2)
            return self._extract_mesh_data()
        finally:
            try:
                gmsh.finalize()
            except Exception:
                pass

    def get_gmsh_log(self) -> list[str]:
        """Return Gmsh log lines accumulated during the last mesh run."""
        try:
            return list(gmsh.logger.get())
        except Exception:
            return []

    @staticmethod
    def classify_error(log_lines: list[str]) -> str:
        """Translate raw Gmsh stderr into a user-readable error message."""
        log_text = "\n".join(log_lines).lower()

        if "self-intersect" in log_text or "self intersection" in log_text:
            surface_match = re.search(r"surface\s+(\d+)", log_text)
            surface_id = surface_match.group(1) if surface_match else "unknown"
            return (
                f"Meshing failed: self-intersecting surface detected near surface {surface_id}. "
                "Try increasing the global element size factor or simplifying the geometry."
            )

        if "edge recovery" in log_text or "recover" in log_text:
            surface_match = re.search(r"surface\s+(\d+)", log_text)
            surface_id = surface_match.group(1) if surface_match else "unknown"
            return (
                f"Meshing failed: could not create a conforming mesh near surface {surface_id}. "
                "The thinnest feature may require a larger element size. "
                "Try: increase size factor to 5% or larger."
            )

        if "size constraint" in log_text or "too small" in log_text:
            return (
                "Meshing failed: element size constraint could not be satisfied. "
                "Try increasing the global element size factor."
            )

        return "Meshing failed. See the log panel for details."

    # ------------------------------------------------------------------
    # private helpers
    # ------------------------------------------------------------------

    def _load_shape(self, geo: GeometryData) -> None:
        import tempfile, os
        from OCC.Core.STEPControl import STEPControl_Writer
        from OCC.Core.IFSelect import IFSelect_RetDone
        from OCC.Core.TopAbs import TopAbs_SOLID, TopAbs_SHELL
        from OCC.Core.BRep import BRep_Builder
        from OCC.Core.TopoDS import TopoDS_Compound
        from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeSolid

        shape = geo.occ_shape

        # If healing returned a shell rather than a solid, attempt to close it.
        # BRepBuilderAPI_MakeSolid wraps shells into a solid for volume meshing.
        if shape.ShapeType() == TopAbs_SHELL:
            try:
                maker = BRepBuilderAPI_MakeSolid()
                maker.Add(shape)
                maker.Build()
                if maker.IsDone():
                    shape = maker.Solid()
            except Exception:
                pass  # fall through with original shell — Gmsh may still mesh it

        with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
            tmp_path = f.name

        try:
            writer = STEPControl_Writer()
            writer.Transfer(shape, 0)  # 0 = STEPControl_AsIs
            status = writer.Write(tmp_path)
            if status != IFSelect_RetDone:
                raise RuntimeError("Failed to write OCC shape to temp STEP for Gmsh import.")

            gmsh.model.occ.importShapes(tmp_path)
            gmsh.model.occ.synchronize()
        finally:
            os.unlink(tmp_path)

    def _set_options(self, geo: GeometryData) -> None:
        target_size = geo.default_element_size() * self._size_factor
        gmsh.option.setNumber("Mesh.CharacteristicLengthMin", target_size * 0.5)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", target_size * 2.0)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 12)
        gmsh.option.setNumber("Mesh.Algorithm", _SURFACE_ALGO)
        gmsh.option.setNumber("Mesh.Algorithm3D", _VOLUME_ALGO)

    def _extract_mesh_data(self) -> MeshData:
        # All node coordinates
        node_tags, coords, _ = gmsh.model.mesh.getNodes()
        nodes = np.array(coords, dtype=np.float64).reshape(-1, 3)
        tag_to_idx = {int(t): i for i, t in enumerate(node_tags)}

        # 3D elements (C3D10 = gmsh type 11 after setOrder(2))
        elem_types, elem_tags, node_tags_flat = gmsh.model.mesh.getElements(3)

        if len(elem_types) == 0:
            raise RuntimeError("Gmsh produced no 3D elements. Check geometry validity.")

        all_connectivity = []
        for etype, _, ntags in zip(elem_types, elem_tags, node_tags_flat):
            props = gmsh.model.mesh.getElementProperties(etype)
            nodes_per_elem = props[3]
            ntags_arr = np.array(ntags, dtype=np.int64).reshape(-1, nodes_per_elem)
            # Remap gmsh 1-based tags to 0-based indices
            remapped = np.vectorize(lambda t: tag_to_idx[int(t)])(ntags_arr)
            all_connectivity.append(remapped)

        connectivity = np.vstack(all_connectivity)
        n_elem = len(connectivity)
        element_types = np.full(n_elem, VTK_QUADRATIC_TETRA, dtype=np.int32)

        return MeshData(
            nodes=nodes,
            connectivity=connectivity,
            element_types=element_types,
        )
