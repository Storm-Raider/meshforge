"""Subprocess entry point for Gmsh meshing.

Invoked by MeshWorker as:
    python _mesh_subprocess.py <payload.pkl> <result.pkl>

Reads a payload dict, runs MeshEngine.mesh_from_step(), writes a result dict.
Runs in its own process so terminating it is instant and leaves the main app clean.
"""
from __future__ import annotations
import sys
import os
import pickle


def main() -> None:
    payload_path, result_path = sys.argv[1], sys.argv[2]

    with open(payload_path, "rb") as f:
        payload = pickle.load(f)

    step_path: str = payload["step_path"]
    default_element_size: float = payload["default_element_size"]
    params_dict: dict = payload["params"]

    log: list[str] = []
    try:
        from meshforge.core.mesh_engine import MeshEngine
        from meshforge.models.mesh_params import MeshParams

        params = MeshParams(**params_dict)
        engine = MeshEngine(params=params)
        mesh_data = engine.mesh_from_step(step_path, default_element_size)
        log = engine.get_gmsh_log()
        result = {"status": "ok", "mesh_data": mesh_data, "log": log}
    except Exception as exc:
        result = {"status": "error", "message": str(exc), "log": log}

    with open(result_path, "wb") as f:
        pickle.dump(result, f)


if __name__ == "__main__":
    main()
