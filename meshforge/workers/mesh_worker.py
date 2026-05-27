from __future__ import annotations
import os
import pickle
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from meshforge.models.geometry_data import GeometryData
from meshforge.models.mesh_data import MeshData
from meshforge.models.mesh_params import MeshParams

_SUBPROCESS_SCRIPT = Path(__file__).parent / "_mesh_subprocess.py"


class MeshWorker(QThread):
    """Spawns a Gmsh subprocess; kills it instantly on Cancel.

    The subprocess runs MeshEngine.mesh_from_step() in its own process so
    terminate() is instant with no Gmsh state corruption in the main app.
    """

    complete = pyqtSignal(object)    # MeshData
    failed = pyqtSignal(str, list)   # user-readable error + gmsh log lines
    progress = pyqtSignal(str)       # status bar text

    def __init__(self, geo: GeometryData, params: MeshParams | None = None, parent=None):
        super().__init__(parent)
        self._geo = geo
        self._params = params or MeshParams()
        self._proc: subprocess.Popen | None = None
        self._cancelled = False

    def request_cancel(self) -> None:
        self._cancelled = True
        self.progress.emit("Cancelling…")
        proc = self._proc
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()

    def was_cancelled(self) -> bool:
        return self._cancelled

    def run(self) -> None:
        tmp_step_path: str | None = None
        tmp_payload_path: str | None = None
        tmp_result_path: str | None = None

        try:
            # 1. Write OCC shape to STEP (shell-to-solid promotion lives here)
            fd, tmp_step_path = tempfile.mkstemp(suffix=".step")
            os.close(fd)
            _write_step(self._geo, tmp_step_path)

            if self._cancelled:
                return

            # 2. Write payload pickle
            payload = {
                "step_path": tmp_step_path,
                "default_element_size": self._geo.default_element_size(),
                "params": asdict(self._params),
            }
            fd, tmp_payload_path = tempfile.mkstemp(suffix=".pkl")
            os.close(fd)
            with open(tmp_payload_path, "wb") as f:
                pickle.dump(payload, f)

            # 3. Create empty result file so the path is reserved
            fd, tmp_result_path = tempfile.mkstemp(suffix=".pkl")
            os.close(fd)

            # 4. Spawn subprocess
            self._proc = subprocess.Popen(
                [sys.executable, str(_SUBPROCESS_SCRIPT),
                 tmp_payload_path, tmp_result_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.progress.emit("Meshing…")

            # 5. Poll until done, emitting elapsed-time progress
            start = time.monotonic()
            while True:
                retcode = self._proc.poll()
                if retcode is not None:
                    break
                elapsed = int(time.monotonic() - start)
                self.progress.emit(f"Meshing… ({elapsed}s)")
                time.sleep(0.2)

            if self._cancelled:
                return

            if retcode != 0:
                self.failed.emit(
                    "Meshing process crashed unexpectedly. See log for details.", []
                )
                return

            # 6. Read result
            try:
                with open(tmp_result_path, "rb") as f:
                    result = pickle.load(f)
            except Exception as exc:
                self.failed.emit(f"Could not read meshing result: {exc}", [])
                return

            if result["status"] == "ok":
                self.complete.emit(result["mesh_data"])
            else:
                log: list[str] = result.get("log", [])
                from meshforge.core.mesh_engine import MeshEngine
                raw = log if log else [result.get("message", "")]
                self.failed.emit(MeshEngine.classify_error(raw), log)

        except Exception as exc:
            if not self._cancelled:
                self.failed.emit(f"Meshing failed: {exc}", [])

        finally:
            for path in (tmp_step_path, tmp_payload_path, tmp_result_path):
                if path:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass


def _write_step(geo: GeometryData, path: str) -> None:
    """Serialize the OCC shape to a STEP file, promoting shells to solids first."""
    from OCC.Core.STEPControl import STEPControl_Writer
    from OCC.Core.IFSelect import IFSelect_RetDone
    from OCC.Core.TopAbs import TopAbs_SHELL, TopAbs_COMPOUND
    from OCC.Core.BRep import BRep_Builder
    from OCC.Core.TopoDS import TopoDS_Compound
    from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
    from OCC.Core.TopExp import TopExp_Explorer

    shape = geo.occ_shape

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

    writer = STEPControl_Writer()
    writer.Transfer(shape, 0)  # STEPControl_AsIs
    status = writer.Write(path)
    if status != IFSelect_RetDone:
        raise RuntimeError("Failed to serialize geometry to STEP for meshing subprocess.")
