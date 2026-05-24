# TODOS.md — MeshForge

Deferred items from the engineering review. Each item includes what, why, and what blocks it.

---

## v2

### Gmsh subprocess model for true Cancel support

**What:** Run Gmsh in a separate Python subprocess. Parent process kills subprocess for instant Cancel; no Gmsh global state corruption.

**Why:** Current v1 design (Cancel = wait for Gmsh to finish, discard result) means a 2-minute mesh locks the user out of cancel-restart for 2 minutes. On 500k+ element assemblies this becomes a usability blocker.

**How to apply:** Replace `MeshWorker(QThread)` with a subprocess launcher. Use multiprocessing pipe or temp file for `MeshData` transfer. Gmsh session lives entirely in subprocess.

**Pros:** True instant Cancel; subprocess crash doesn't kill the main app; bypasses Python GIL for meshing performance.

**Cons:** ~3 days human effort. Requires IPC for `MeshData` serialization. More complex than QThread pattern.

**Depends on:** v1 ships first. Collect user feedback — only build this if cancel latency is a confirmed pain point.

---

### vtkThreshold geometric isolation of failing elements

**What:** Add a mode that geometrically removes passing elements from the viewport so only failing elements are visible in 3D space.

**Why:** For thick solid parts, failing elements can be buried inside the geometry and invisible on the surface color display. Spatial isolation helps the engineer find where failures occur, not just that they exist.

**How to apply:** Add "Isolate Failures" toggle to quality panel. `vtkThreshold.ThresholdByLower(0.3)` → new actor showing only elements with Jacobian < 0.3. Run filter in QThread with progress indicator.

**Pros:** Matches element selection capability in HyperMesh; more informative for complex solid geometry.

**Cons:** 150-400ms per threshold operation at 500k elements. VTK threshold pipeline needs to run off main thread.

**Depends on:** v1 ships. Only build if users report "I can see the color but can't find where it is."

---

## v1.1

### Full Abaqus 2023 .inp keyword validator (conditional)

**What:** Implement an Abaqus-specific .inp format validator beyond what Gmsh's built-in writer produces. Validates: continuation line rules (max 16 entries per data line), `*SOLID SECTION` / `*MATERIAL` keyword format, `*HEADING` block, C3D10 element type naming for Abaqus 2023.

**Why:** v1 export is tested on CalculiX. If the Week 0 Abaqus round-trip test (added to Week 0 Task A) passes with Gmsh's built-in writer, this item is closed. If it fails, this is the implementation path to full Abaqus 2023 format compatibility.

**How to apply:** Parse the output of `gmsh.write()` with a custom Abaqus keyword parser. Compare against Abaqus Input Data Reference 2023. Fix any keyword format mismatches in a custom `AbaqusInpWriter` that wraps Gmsh's output.

**Pros:** Removes "tested on CalculiX" qualifier; CI can run Abaqus Academic validation.

**Cons:** ~3 days human effort. Requires Abaqus license (Academic is free, apply at Dassault Systèmes). Requires reading Abaqus Input Data Reference manual.

**Depends on:** Week 0 Abaqus round-trip test result. Only execute if that test fails.
