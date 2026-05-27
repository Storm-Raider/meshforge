from __future__ import annotations
import re
import threading
import numpy as np

from meshforge.models.geometry_data import GeometryData
from meshforge.models.mesh_data import MeshData
from meshforge.models.mesh_params import MeshParams

# VTK element type for 10-node quadratic tetrahedron (C3D10)
VTK_QUADRATIC_TETRA = 24

_GMSH_LOCK = threading.Lock()


class MeshEngine:
    """Generates a C3D10 tet mesh from a GeometryData OCC shape via Gmsh.

    No Qt imports. One active instance per process (Gmsh global state).
    The caller (MeshWorker) is responsible for checking cancel_requested
    after this returns, and discarding the result if set.
    """

    def __init__(self, params: MeshParams | None = None):
        self._params = params or MeshParams()
        self._last_gmsh_log: list[str] = []

    def mesh(self, geo: GeometryData) -> MeshData:
        """Run full surface + volume mesh. Returns MeshData with no quality_scalars."""
        with _GMSH_LOCK:
            return self._mesh_locked(geo)

    def _mesh_locked(self, geo: GeometryData) -> MeshData:
        import gmsh
        import signal as _signal
        import threading

        # gmsh.initialize() calls signal.signal(SIGINT, ...) which Python only
        # permits from the main thread.  Stub it out when called from a worker.
        _in_worker = threading.current_thread() is not threading.main_thread()
        if _in_worker:
            _orig_signal = _signal.signal
            _signal.signal = lambda *a, **kw: None
        try:
            gmsh.initialize()
        finally:
            if _in_worker:
                _signal.signal = _orig_signal

        gmsh.logger.start()
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("General.Verbosity", 3)
        gmsh.model.add("meshforge")

        try:
            self._load_shape(geo)
            self._set_options(geo)
            gmsh.model.mesh.generate(3)
            gmsh.model.mesh.setOrder(2)
            return self._extract_mesh_data()
        finally:
            # Capture log before finalize — logger is unavailable after finalize()
            try:
                self._last_gmsh_log = list(gmsh.logger.get())
            except Exception:
                self._last_gmsh_log = []
            try:
                gmsh.finalize()
            except Exception:
                pass

    def get_gmsh_log(self) -> list[str]:
        """Return Gmsh log lines from the last mesh run."""
        return list(self._last_gmsh_log)

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

        if "plc error" in log_text or "segment and a facet intersect" in log_text:
            return (
                "Meshing failed: surface mesh self-intersection detected. "
                "This often occurs with multi-body assemblies whose parts touch or overlap. "
                "Try increasing the element size factor to improve surface mesh quality."
            )

        return "Meshing failed. See the log panel for details."

    # ------------------------------------------------------------------
    # private helpers
    # ------------------------------------------------------------------

    def _load_shape(self, geo: GeometryData) -> None:
        import gmsh
        import tempfile, os
        from OCC.Core.STEPControl import STEPControl_Writer
        from OCC.Core.IFSelect import IFSelect_RetDone
        from OCC.Core.TopAbs import TopAbs_SHELL, TopAbs_COMPOUND
        from OCC.Core.BRep import BRep_Builder
        from OCC.Core.TopoDS import TopoDS_Compound
        from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
        from OCC.Core.TopExp import TopExp_Explorer

        shape = geo.occ_shape

        # Promote shells to solids so Gmsh can produce closed 3D volumes.
        # Handles two cases:
        #  - Top-level shell (e.g. healed single-body STEP)
        #  - Compound of shells (e.g. multi-body assembly STEP with no solid wrapper)
        def _shell_to_solid(shell):
            maker = BRepBuilderAPI_MakeSolid()
            maker.Add(shell)
            maker.Build()
            return maker.Solid() if maker.IsDone() else shell

        if shape.ShapeType() == TopAbs_SHELL:
            try:
                shape = _shell_to_solid(shape)
            except Exception:
                pass

        elif shape.ShapeType() == TopAbs_COMPOUND:
            exp = TopExp_Explorer(shape, TopAbs_SHELL)
            if exp.More():
                builder = BRep_Builder()
                compound = TopoDS_Compound()
                builder.MakeCompound(compound)
                while exp.More():
                    try:
                        builder.Add(compound, _shell_to_solid(exp.Current()))
                    except Exception:
                        builder.Add(compound, exp.Current())
                    exp.Next()
                shape = compound

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

            # Multi-body assemblies produce separate volumes whose shared/overlapping
            # boundaries cause PLC errors during volume meshing.  Fragment splits them
            # into conforming sub-volumes with shared interfaces.
            vols = gmsh.model.occ.getEntities(3)
            if len(vols) > 1:
                gmsh.model.occ.fragment(vols, [])
                gmsh.model.occ.synchronize()
        finally:
            os.unlink(tmp_path)

    def _set_options(self, geo: GeometryData) -> None:
        import gmsh
        p = self._params
        target_size = geo.default_element_size() * p.size_factor
        min_size = p.min_size if p.min_size is not None else target_size * 0.5
        max_size = p.max_size if p.max_size is not None else target_size * 2.0
        gmsh.option.setNumber("Mesh.CharacteristicLengthMin", min_size)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", max_size)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", p.curvature_refinement)
        gmsh.option.setNumber("Mesh.Algorithm", p.surface_algorithm)
        gmsh.option.setNumber("Mesh.Algorithm3D", p.volume_algorithm)

    def _extract_mesh_data(self) -> MeshData:
        import gmsh
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
