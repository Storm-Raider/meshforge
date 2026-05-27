from __future__ import annotations
from PyQt6.QtCore import QThread, pyqtSignal

from meshforge.core.mesh_engine import MeshEngine
from meshforge.models.geometry_data import GeometryData
from meshforge.models.mesh_data import MeshData
from meshforge.models.mesh_params import MeshParams


class MeshWorker(QThread):
    """Thin QThread wrapper around MeshEngine.

    Emits complete(MeshData) on success, failed(str) on error.
    Cancel behavior: sets cancel_requested; worker completes the current Gmsh
    run then checks the flag. Caller must check was_cancelled() and discard result.
    Do NOT call QThread.terminate() — corrupts Gmsh global state.
    """

    complete = pyqtSignal(object)    # MeshData
    failed = pyqtSignal(str, list)   # user-readable error message + raw gmsh log lines
    progress = pyqtSignal(str)       # status text updates ("Meshing…", "Cancelling…")

    def __init__(self, geo: GeometryData, params: MeshParams | None = None, parent=None):
        super().__init__(parent)
        self._geo = geo
        self._params = params or MeshParams()
        self._cancel_requested = False

    def request_cancel(self) -> None:
        self._cancel_requested = True
        self.progress.emit("Cancelling… (waiting for Gmsh)")

    def was_cancelled(self) -> bool:
        return self._cancel_requested

    def run(self) -> None:
        try:
            engine = MeshEngine(params=self._params)
            result = engine.mesh(self._geo)

            if self._cancel_requested:
                return   # discard result silently

            self.complete.emit(result)
        except Exception as e:
            if self._cancel_requested:
                return
            try:
                gmsh_log = engine.get_gmsh_log()
            except Exception:
                gmsh_log = []
            user_msg = MeshEngine.classify_error(gmsh_log if gmsh_log else [str(e)])
            self.failed.emit(user_msg, gmsh_log)
