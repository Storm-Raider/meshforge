# MeshForge — Week 0 Validation Scripts

Run these before writing any application code. All three are blocking gates.

---

## Setup (do once)

```bash
conda create -n meshforge-week0 python=3.11 -c conda-forge
conda activate meshforge-week0
conda install -c conda-forge gmsh pythonocc-core vtk pyqt6 numpy matplotlib
```

Verify the critical import (Task B validation):
```bash
python -c "import OCC.Core.BRep; import vtk; from PyQt6 import QtWidgets; import gmsh; print('ALL OK')"
```

If this fails: stop. Fix before running any scripts.

---

## Task A — Gmsh Algorithm3D Benchmark

**What:** Meshes your STEP file with Algorithm3D=1 (Delaunay) and Algorithm3D=9 (HXT), computes scaled Jacobian for both, prints a side-by-side quality summary, and saves `.msh` + `.inp` files.

```bash
conda activate meshforge-week0
python task_a_gmsh_benchmark.py /path/to/your_production_part.step
```

**Outputs:**
- `your_part_delaunay.inp` — use for Task E Abaqus round-trip (Delaunay run)
- `your_part_hxt.inp` — use for Task E Abaqus round-trip (HXT run)
- `your_part_jacobian_comparison.png` — histogram to share with engineers

**Decision:** The script prints a recommendation. Record the winning algorithm and update the design doc meshing spec before starting T5 (MeshWorker).

**Then:** Send the winning mesh (or both) to 3 senior CAE engineers. Ask: *"Is this good enough to run a structural simulation on?"* Record answers — not impressions.

---

## Task B — Installer Validation (manual)

**What:** Build and test the conda constructor installer on a clean Windows VM.

1. Create `tests/fixtures/bracket_clean.step` (use any production STEP file you have; rename it)
2. On a clean Windows VM (no conda, no Python):
   ```
   conda install -c conda-forge constructor
   cd week0
   constructor .
   ```
3. Copy the resulting `.exe` to the clean VM and run it
4. Verify the wizard UI appears (not a command-prompt window)
5. Test silent install: `MeshForge-0.1.0-Windows-x86_64.exe /S`
6. Verify install path is `%LOCALAPPDATA%\meshforge`
7. Note any AV alerts — document for IT exception template

**See:** `construct_template.yaml` for the full spec and checklist.

---

## Task C — VTK Render Benchmark

**What:** Builds a synthetic 500k C3D10 mesh in memory, runs the full VTK render pipeline (geometry filter → scalar assignment → Render()), and measures timing for each step.

```bash
conda activate meshforge-week0
python task_c_vtk_benchmark.py
python task_c_vtk_benchmark.py --elements 100000   # faster first pass
```

**Pass criteria:**
| Measurement | Must be |
|-------------|---------|
| First Render() after scalar assignment | < 500ms |
| SetTableRange() + Render() (filter interaction) | < 50ms |
| Full scalar update + Render() | < 500ms |

A window opens for ~3 seconds showing the colored mesh, then closes automatically.

**If FAIL:** The script prints specific next steps. Do not start T7 (VTK render pipeline) until this passes or you have a fix.

---

## Task D — Name the price (ongoing)

In every conversation where an engineer evaluates the mesh, ask:

> *"If this were a $1,500/year subscription to get Abaqus export, would you sign up?"*

Record: yes / no / maybe. "Maybe" counts as no.

---

## Task E — Abaqus Round-trip (manual)

Use the `.inp` files produced by Task A:

1. Open Abaqus (Professional or Academic)
2. File → Import → Model → select `your_part_hxt.inp` (or delaunay)
3. Set up a simple static step: fixed face + point load
4. Submit job, check for keyword errors in the `.dat` / `.msg` file
5. If job completes: label becomes "tested on Abaqus 2023"
6. If keyword errors: record the specific errors in `TODOS.md` (v1.1 Abaqus validator path is already documented there)
