# Changelog

All notable changes to MeshForge are documented here.

---

## v0.3.0 — 2026-05-28

### Added

**Additional element types**
- Linear Tet (C3D4): 4-node tetrahedral elements for explicit dynamics solvers. `MeshParams(mesh_type="lintet")`. Exported as C3D4 in `.inp` and CTETRA-4 in `.nas`
- Hex meshing (C3D8): linear hexahedral elements via Gmsh barycentric subdivision. `MeshParams(mesh_type="hex")`. Exported as C3D8 in `.inp` and CHEXA-8 in `.nas`
- `QualityEngine` handles all three tet types (C3D4, C3D10) using shared `_compute_tet_corners()` and hex type (C3D8) separately

**Mesh optimization**
- Laplacian + gradient-descent smoothing via `gmsh.model.mesh.optimize()`. `MeshParams(smooth_iter=N)` runs N passes after meshing. Works for tet and hex. Repositions nodes without changing topology.

**Surface mesh preview**
- "Preview Surface" button runs a fast 2D surface mesh (triangles + quads) in a background thread and displays it with steel-blue flat shading and edge lines. Lets the user validate element density and refinement zones before committing to a full 3D volume mesh. Status bar shows triangle count and node count.

**UI / visualization**
- Scalar bar (color legend) in the viewport, showing the Jacobian color scale
- Camera preset shortcuts: numpad 1 (front), 3 (right), 7 (top), F (fit all)
- Jacobian histogram in the quality panel
- Mesh size presets in the mesh panel

### Fixed

- `InpExporter` and `NasExporter` now export C3D4 and C3D6 (wedge) elements correctly
- CTETRA-10 Gmsh→Nastran node permutation: conn[8] and conn[9] were swapped (corner-midpoint ordering mismatch). Fixed permutation `[0,1,2,3,4,5,6,7,9,8]`

### Tests

- 26 new tests: hex meshing, lintet meshing, smoothing, surface mesh, quality engine lintet. Total: 83 tests

---

## v0.2.0 — 2026-05-27

### Added

**Local mesh refinement zones**
- `RefinementZone` dataclass: per-feature mesh density control via `entity_type` (surface/edge), `entity_index` (1-based), `size_factor` (0.1–1.0× global), and `influence_radius` (STEP file units)
- Gmsh Distance + Threshold + Min sizing fields applied in `MeshEngine._set_options()` when zones are present. Fine mesh within `influence_radius × 0.1` of the entity, linearly ramping back to global size at `influence_radius`
- `CharacteristicLengthExtendFromBoundary` disabled only when zones are active — zero change to baseline mesh output when no zones are set
- Stale zone indices (entity removed after STEP reload) are silently skipped; meshing continues with remaining valid zones
- Refinement Zones panel in mesh settings: Add/Remove zone rows, each with Surface/Edge selector, index spinbox, size factor, and influence radius

**Nastran .nas export**
- `NasExporter`: Nastran Bulk Data free-field format. GRID cards (`%.6g` coordinates), CTETRA-10 with 8+4 field continuation split (EID+PID+G1–G6 on line 1, `+,G7–G10` on continuation), MAT1 steel placeholder (E=210 GPa, nu=0.3), PSOLID, ENDDATA
- Export dialog now offers Abaqus `.inp` / Nastran `.nas` format selection
- Material placeholder warning shown in log panel and as a `$` comment in the exported file

**Model tree**
- Edge count shown in geometry subtree (populated from OCC at import time)

**Tests**
- 25 new tests: `RefinementZone` unit tests, subprocess serialization round-trip, `NasExporter` format correctness (GRID count, CTETRA continuation split, ENDDATA, 1-based node IDs), mesh-engine integration tests with zones and stale-zone skip. Total: 57 tests

### Fixed

- Subprocess deserialization: `dataclasses.asdict()` converts `RefinementZone` objects to plain dicts; `_mesh_subprocess.py` now reconstructs `RefinementZone(**z)` before building `MeshParams` — previously would have crashed with `AttributeError` on first zone use

### Known limitations

- Refinement zone surface/edge identification is index-based (trial and error). Surface highlight on hover is planned for v0.3
- Zone `influence_radius` is in STEP file units; MeshForge displays "STEP units" as a hint — full unit detection is v0.3

---

## v0.1.0 — 2026-05-24

Initial release. Full pipeline from STEP import to C3D10 mesh to Abaqus `.inp` export.

### Added

**Core pipeline**
- STEP import via pythonocc-core (AP203 and AP214). OCC healing with `BRepBuilderAPI_Sewing` + `ShapeFix_Shape`. Automatic shell→solid promotion via `BRepBuilderAPI_MakeSolid` for open-shell STEP files
- C3D10 quadratic tetrahedral meshing via Gmsh 4.13. Surface algorithm: Frontal-Delaunay (6). Volume algorithm: HXT (9) — benchmark on 20 production STEP files showed 99.1% pass rate vs 97.1% for Delaunay
- Scaled Jacobian quality metric using product-of-column-norms formula: `det(J) / (‖col₀‖ × ‖col₁‖ × ‖col₂‖)`. Pass threshold: 0.3. Warn threshold: 0.1. Perfect equilateral tetrahedron scores ≈ 0.707
- Abaqus `.inp` export (C3D10 element type, 1-based node IDs, `*NODE` + `*ELEMENT` blocks). Export requires a license; geometry + quality review are free
- Global element size factor control (0.1–5.0×). Default: 1.0 (≈3% of bounding box diagonal, capped at 50% of minimum edge length). `MeshSizeFromCurvature = 12` for automatic refinement at curved surfaces

**UI**
- PyQt6 main window with state machine (empty → loading → success/partial/error)
- VTK 9 viewport with blue→red Jacobian color scale. Gray for elements below the quality threshold slider
- Quality panel: pass/warn/fail element counts and percentages, min/mean/max Jacobian
- Model tree: surface count, bounding box diagonal, minimum edge length, healing status
- Log panel: full Gmsh output with error classification
- Drag-and-drop STEP import onto the viewport
- "Try with sample geometry" first-run CTA (loads `bracket_clean.step`)
- Cancel with graceful Gmsh wait (`"Cancelling… (waiting for Gmsh)"`)
- GPU startup check: detects OpenGL < 3.2 before the window opens, shows error dialog and exits cleanly
- Help menu: Documentation, Report a Bug, About

**Tests**
- 32 tests across models, core, and export layers. All passing on Linux (aarch64) and Windows (x86_64)
- GitHub Actions CI: runs on every push and PR to `main`

### Known limitations

- Single STEP body only — multi-body assemblies are imported as a single merged solid
- C3D10 elements only — shell and beam elements not supported
- Cancel waits for current Gmsh operation to finish (up to ~30 s on large geometry). True instant cancel is a v2 item
- Export tested against CalculiX and Abaqus 2023. Older Abaqus versions (< 6.14) are untested

---

*MeshForge uses [Gmsh](https://gmsh.info) for meshing, [Open CASCADE Technology](https://dev.opencascade.org) for geometry healing, and [VTK](https://vtk.org) for visualization.*
