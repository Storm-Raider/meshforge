# TODOS.md — MeshForge

Deferred items from engineering reviews. Each item includes what, why, and what blocks it.

---

## v0.3

### VTK surface highlight on refinement zone hover

**What:** When the user changes the zone entity combobox index, highlight the corresponding surface or edge in the VTK viewport (e.g., temporary orange overlay actor).

**Why:** Current v0.2 UX is index-based trial-and-error — select index, re-mesh, observe. Highlight-on-hover removes the re-mesh step for entity identification.

**Depends on:** v0.2 ships. Build once users report difficulty identifying surfaces by index.

---

### Shell elements (S4R / S3)

**What:** Add surface meshing for thin-walled structures via Gmsh's `mesh.generate(2)` path. Export as Abaqus S4R / S3 or Nastran CQUAD4 / CTRIA3.

**Why:** Thin-walled structural jobs (sheet metal, pressure vessels, chassis) require shell elements. This is the largest capability gap vs. HyperMesh. Every thin-walled job the founder runs with MeshForge that hits this wall is a data point.

**Depends on:** Track how many of the next 10 real FEA jobs need shells. Build when that count reaches 3+.

---

## v1.1

### Full Abaqus 2023 .inp keyword validator (conditional)

**What:** Implement an Abaqus-specific .inp format validator beyond what the current writer produces. Validates: continuation line rules (max 16 entries per data line), `*SOLID SECTION` / `*MATERIAL` keyword format, `*HEADING` block, C3D10 element type naming for Abaqus 2023.

**Why:** v1 export is tested on CalculiX. If the Week 0 Abaqus round-trip test (Task E) passes, this item is closed. If it fails, this is the implementation path to full Abaqus 2023 format compatibility.

**Depends on:** Week 0 Task E (Abaqus round-trip) result. Only execute if that test fails.

---

## Done

- **v2: Gmsh subprocess model for instant Cancel** — shipped `7e94cef`. `MeshWorker` spawns a subprocess; `terminate()` is instant with no Gmsh state corruption in main app.
- **v2: vtkThreshold geometric isolation of failing elements** — shipped `ed1a7cf`. "Isolate Failures" toggle in quality panel, `vtkThreshold` filter run off main thread.
- **v0.2: CTETRA-10 Gmsh→Nastran node permutation** — verified and fixed `ec67c2c`. Gmsh conn[8]/conn[9] are swapped vs Nastran QRG; corrected in NasExporter. Verified against 5,051 elements.
- **v0.2: STEP reload zone clearing** — implemented in `MeshPanel.set_geometry()`. Existing zones are auto-cleared when a new STEP file is imported.
