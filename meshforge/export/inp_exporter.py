from __future__ import annotations
import re
import tempfile
import os
from pathlib import Path

import gmsh
import numpy as np

from meshforge.models.geometry_data import GeometryData
from meshforge.models.mesh_data import MeshData


class InpExporter:
    """Exports MeshData to Abaqus .inp via Gmsh's built-in writer + CalculiX validator.

    No Qt imports.
    """

    def export(self, mesh: MeshData, geo: GeometryData, dest_path: str | Path) -> list[str]:
        """Write .inp to dest_path. Returns list of validation warnings (empty = clean).

        Raises RuntimeError on write failure or validation-blocking errors.
        """
        dest_path = Path(dest_path)
        self._check_writable(dest_path)

        # Re-mesh via Gmsh to produce the .inp — Gmsh's own writer handles
        # all keyword formatting. We then validate the output file.
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
        parent = path.parent
        if not parent.exists():
            raise RuntimeError(
                f"Export failed: directory {parent} does not exist."
            )
        # Test write access
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
        """Use Gmsh to write the .inp, capturing output via a temp file."""
        import threading

        with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as step_f:
            step_path = step_f.name
        with tempfile.NamedTemporaryFile(suffix=".inp", delete=False) as inp_f:
            inp_path = inp_f.name

        try:
            # Write OCC shape to temp STEP
            from OCC.Core.STEPControl import STEPControl_Writer
            from OCC.Core.IFSelect import IFSelect_RetDone
            writer = STEPControl_Writer()
            writer.Transfer(geo.occ_shape, 0)
            writer.Write(step_path)

            # Re-mesh and export with Gmsh
            gmsh.initialize()
            gmsh.option.setNumber("General.Terminal", 0)
            gmsh.model.add("meshforge_export")
            gmsh.model.occ.importShapes(step_path)
            gmsh.model.occ.synchronize()

            # Apply same mesh parameters used during original meshing
            target_size = geo.default_element_size()
            gmsh.option.setNumber("Mesh.CharacteristicLengthMin", target_size * 0.5)
            gmsh.option.setNumber("Mesh.CharacteristicLengthMax", target_size * 2.0)
            gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 12)
            gmsh.option.setNumber("Mesh.Algorithm", 6)
            gmsh.option.setNumber("Mesh.Algorithm3D", 9)

            gmsh.model.mesh.generate(3)
            gmsh.model.mesh.setOrder(2)
            gmsh.write(inp_path)
            gmsh.finalize()

            return Path(inp_path).read_text(encoding="ascii")
        finally:
            for p in (step_path, inp_path):
                try:
                    os.unlink(p)
                except OSError:
                    pass

    def _validate(self, inp_text: str, mesh: MeshData) -> list[str]:
        """Run CalculiX-compatibility checks. Returns warning strings."""
        warnings = []

        # Check *ELEMENT block exists
        if "*ELEMENT" not in inp_text.upper():
            warnings.append("No *ELEMENT block found in exported .inp")

        # Check *NODE block exists
        if "*NODE" not in inp_text.upper():
            warnings.append("No *NODE block found in exported .inp")

        # Check element type is C3D10 (second-order tet)
        if re.search(r"TYPE\s*=\s*C3D4\b", inp_text, re.IGNORECASE):
            warnings.append(
                "Export contains C3D4 first-order elements. "
                "MeshForge should export C3D10 only — check setOrder(2) was applied."
            )

        # Check for excessive line length (Abaqus limit: 80 chars per continuation line)
        for i, line in enumerate(inp_text.splitlines(), 1):
            if len(line) > 256:
                warnings.append(f"Line {i} exceeds 256 characters — may cause Abaqus parse errors.")
                break  # report first occurrence only

        return warnings
