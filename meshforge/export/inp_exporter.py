from __future__ import annotations
import re
from pathlib import Path

import numpy as np

from meshforge.models.geometry_data import GeometryData
from meshforge.models.mesh_data import MeshData

_VTK_C3D4  = 10
_VTK_C3D10 = 24
_VTK_C3D8  = 12
_VTK_C3D6  = 13


class InpExporter:
    """Exports MeshData to Abaqus .inp format.

    No Qt imports. Writes directly from MeshData — no re-meshing.
    Supports C3D10 (quadratic tet) and C3D8 (linear hex) element types.
    """

    def export(self, mesh: MeshData, geo: GeometryData, dest_path: str | Path) -> list[str]:
        """Write .inp to dest_path. Returns list of validation warnings (empty = clean).

        Raises RuntimeError on write failure or validation-blocking errors.
        """
        dest_path = Path(dest_path)
        self._check_writable(dest_path)

        inp_text = self._generate_inp(mesh, geo)

        try:
            dest_path.write_text(inp_text, encoding="ascii")
        except OSError as e:
            raise RuntimeError(
                f"Export failed: could not write to {dest_path}. "
                "Check: disk space, file permissions, and whether the file is "
                "already open in another application."
            ) from e

        return self._validate(inp_text, mesh)

    # ------------------------------------------------------------------
    # private helpers
    # ------------------------------------------------------------------

    def _check_writable(self, path: Path) -> None:
        import os
        parent = path.parent
        if not parent.exists():
            raise RuntimeError(
                f"Export failed: directory {parent} does not exist."
            )
        test = path.parent / f".meshforge_write_test_{os.getpid()}"
        try:
            test.touch()
            test.unlink()
        except OSError:
            raise RuntimeError(
                f"Export failed: could not write to {path}. "
                "Check: disk space, file permissions."
            )

    def _generate_inp(self, mesh: MeshData, geo: GeometryData) -> str:
        lines: list[str] = []
        lines.append("*Heading")
        lines.append(" MeshForge export")

        lines.append("*NODE")
        for i, (x, y, z) in enumerate(mesh.nodes, 1):
            lines.append(f"{i}, {x:.10g}, {y:.10g}, {z:.10g}")

        # Group elements by VTK type
        unique_types = np.unique(mesh.element_types)
        elset_names: list[str] = []

        for vtk_type in unique_types:
            mask = mesh.element_types == vtk_type
            indices = np.where(mask)[0]

            if vtk_type == _VTK_C3D10:
                abaqus_type = "C3D10"
                elset = "TetElements"
            elif vtk_type == _VTK_C3D8:
                abaqus_type = "C3D8"
                elset = "HexElements"
            elif vtk_type == _VTK_C3D4:
                abaqus_type = "C3D4"
                elset = "TetBulkElements"
            elif vtk_type == _VTK_C3D6:
                abaqus_type = "C3D6"
                elset = "PrismElements"
            else:
                continue

            elset_names.append(elset)
            lines.append(f"*ELEMENT, type={abaqus_type}, ELSET={elset}")
            for local_i, global_i in enumerate(indices, 1):
                conn = mesh.connectivity[global_i]
                # Strip -1 padding (mixed connectivity) and use only valid nodes
                valid = conn[conn >= 0]
                node_ids = ", ".join(str(int(n) + 1) for n in valid)
                lines.append(f"{global_i}, {node_ids}")

        if elset_names:
            # Combine all element sets into one "Solid" set
            lines.append(f"*ELSET, ELSET=Solid")
            lines.append(", ".join(elset_names))

        lines.append("*NSET, NSET=AllNodes, GENERATE")
        lines.append(f"1, {mesh.node_count}")

        return "\n".join(lines) + "\n"

    def _validate(self, inp_text: str, mesh: MeshData) -> list[str]:
        warnings = []

        if "*NODE" not in inp_text.upper():
            warnings.append("No *NODE block found in exported .inp")

        if "*ELEMENT" not in inp_text.upper():
            warnings.append("No *ELEMENT block found in exported .inp")

        known_types = {"C3D10", "C3D8", "C3D4", "C3D6"}
        has_any = any(
            bool(re.search(rf"TYPE\s*=\s*{t}\b", inp_text, re.IGNORECASE))
            for t in known_types
        )
        if not has_any:
            warnings.append("Export contains no recognized element types — check mesh type.")

        return warnings
