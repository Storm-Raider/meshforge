from __future__ import annotations
import re
from pathlib import Path

import numpy as np

from meshforge.models.geometry_data import GeometryData
from meshforge.models.mesh_data import MeshData


class InpExporter:
    """Exports MeshData to Abaqus .inp format.

    No Qt imports. Writes directly from MeshData — no re-meshing.
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
        """Write Abaqus .inp directly from MeshData — no re-meshing.

        Exports the exact mesh that was quality-checked and rendered.
        """
        lines: list[str] = []
        lines.append("*Heading")
        lines.append(" MeshForge export")

        lines.append("*NODE")
        for i, (x, y, z) in enumerate(mesh.nodes, 1):
            lines.append(f"{i}, {x:.10g}, {y:.10g}, {z:.10g}")

        # C3D10: 10-node quadratic tet — connectivity is (E, 10) int64, 0-based
        lines.append("*ELEMENT, type=C3D10, ELSET=Solid")
        for i, conn in enumerate(mesh.connectivity, 1):
            node_ids = ", ".join(str(int(n) + 1) for n in conn)
            lines.append(f"{i}, {node_ids}")

        lines.append("*ELSET, ELSET=Solid, GENERATE")
        lines.append(f"1, {mesh.element_count}")

        lines.append("*NSET, NSET=AllNodes, GENERATE")
        lines.append(f"1, {mesh.node_count}")

        return "\n".join(lines) + "\n"

    def _validate(self, inp_text: str, mesh: MeshData) -> list[str]:
        """Run CalculiX-compatibility checks. Returns warning strings."""
        warnings = []

        if "*NODE" not in inp_text.upper():
            warnings.append("No *NODE block found in exported .inp")

        if "*ELEMENT" not in inp_text.upper():
            warnings.append("No *ELEMENT block found in exported .inp")

        if not re.search(r"TYPE\s*=\s*C3D10\b", inp_text, re.IGNORECASE):
            warnings.append(
                "Export does not contain C3D10 elements — structural FEA requires "
                "quadratic tetrahedral elements."
            )

        if re.search(r"TYPE\s*=\s*C3D4\b", inp_text, re.IGNORECASE):
            warnings.append(
                "Export contains C3D4 first-order elements. "
                "MeshForge should export C3D10 only."
            )

        return warnings
