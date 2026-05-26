# FAQ and Troubleshooting

---

## Installation

### `No module named 'gmsh'` after conda install

On some platforms (aarch64 Linux, certain Windows builds) the conda-forge `gmsh` package installs the command-line binary but not the Python API wrapper. Fix:

```bash
conda activate meshforge
pip install gmsh==4.13.1
```

This installs the pure-Python wheel on top of the conda binary. The two coexist without conflict.

### `No module named 'OCC'` or `pythonocc-core` import errors

pythonocc-core is only available on conda-forge — it is not on PyPI. Make sure you created the environment from `environment.yml` using conda, not pip:

```bash
conda env create -f environment.yml   # correct
pip install -r requirements.txt       # will not work
```

### Conda solve takes 10+ minutes

Use mamba for faster solves:

```bash
conda install -n base -c conda-forge mamba
mamba env create -f environment.yml
```

### `OpenGL 3.2 not available` on launch

MeshForge requires OpenGL 3.2. Common causes and fixes:

| Situation | Fix |
|---|---|
| Windows, outdated GPU driver | Update driver from GPU vendor site |
| Windows VM / Remote Desktop | Enable GPU passthrough or use a physical machine |
| Linux headless server | Install a virtual display: `sudo apt install xvfb`, run `Xvfb :99 & DISPLAY=:99 meshforge` |
| Raspberry Pi / embedded GPU | Not supported — VideoCore and Mali GPUs max out at OpenGL ES 3.1 |

---

## Geometry Import

### `failed: BRepCheck invalid solid`

OCC could not produce a valid closed solid from the STEP file. Common causes:

- Open shell (missing faces) — the geometry has gaps or missing surfaces
- Self-intersecting faces — usually from boolean operations that barely touch
- Non-manifold edges — an edge shared by more than two faces

Fix in CAD: run a geometry check/heal tool (Spaceclaim "Check Geometry", Solidworks "Check", CATIA "Geometry Analysis"). Export as a single closed solid body.

### Healing status shows `warn: sewing gap <N> mm`

MeshForge sewed together geometry gaps up to 1 mm. This is normal for imported assemblies. The mesh will proceed — verify that the meshed surface is watertight in the viewport before exporting.

### Import is very slow (>30 s for a small file)

OCC healing scales with the number of faces. For complex assemblies with hundreds of surfaces, 30–60 s is normal. If it exceeds 5 minutes, the geometry likely has degenerate geometry (zero-area faces, near-duplicate vertices). Simplify in CAD before importing.

---

## Meshing

### "Self-intersecting surface detected near surface N"

The geometry has overlapping or penetrating faces. Workarounds:

1. Increase the size factor to 2.0 or higher — larger elements may span the intersection
2. In CAD: find surface N using the surface ID and fix the intersection
3. If the intersection is cosmetic (e.g. fillet nearly touching a wall), suppress the feature

### "Could not create a conforming mesh near surface N"

Gmsh cannot create elements that conform to a very thin feature. Options:

1. Increase the size factor to 5% or larger (`size_factor >= 1.5` for most thin-wall parts)
2. In CAD: suppress features thinner than 2× your target element size
3. Switch to shell elements for thin-walled sheet metal (not yet supported in v1 — planned for v2)

### "Element size constraint could not be satisfied"

The minimum and maximum size bounds conflict, usually because `min_edge_length` on the geometry is extremely small (dust faces, slivers). Fix:

1. Increase the size factor slider
2. In CAD: remove sliver faces and short edges using defeaturing tools

### "Gmsh produced no 3D elements"

The geometry imported as an open shell rather than a closed solid. Causes:

- STEP file exported as a surface body instead of a solid body
- OCC healing returned a shell that MeshForge could not close

Fix: re-export from CAD explicitly as a solid body (not sheet, not surface). In Solidworks: File → Save As → STEP, ensure "Export solid bodies" is checked.

### Meshing succeeds but takes very long (>5 minutes)

Normal for: assemblies with many small features, geometries with large aspect ratios, or size factors below 0.5. Expected times on a modern desktop GPU:

| Geometry complexity | Size factor 1.0 | Size factor 0.5 |
|---|---|---|
| Simple bracket (~20 surfaces) | 15–30 s | 60–120 s |
| Engine block (~200 surfaces) | 2–5 min | 10–20 min |
| Full assembly (>500 surfaces) | 5–15 min | 30–60 min |

Use **Cancel** to abort and increase the size factor if needed.

---

## Quality

### Almost all elements show red (Jacobian < 0.1)

This usually means a geometry problem rather than a mesh problem. Check:

1. Are there very thin features? Flat tetrahedra form near thin walls
2. Is the healing status `warn`? A poorly healed solid can produce degenerate elements near gaps
3. Try increasing the size factor — very fine meshes on coarse geometry amplify quality problems near features

### Mean Jacobian is < 0.3 for a clean-looking geometry

The scaled Jacobian for C3D10 elements measures corner-node geometry only (mid-side nodes are ignored in the quality computation). A mean of 0.3–0.5 is typical for production Abaqus meshes. Values above 0.6 indicate excellent quality. Values below 0.2 may warrant mesh refinement or geometry simplification near sharp corners.

### The quality panel shows 0 elements

Meshing completed but the quality pass has not run yet, or was cancelled. Click **Remesh** to rerun the full pipeline.

---

## Export

### Export button is greyed out

Export requires:
1. A successful mesh (quality colors visible in viewport)
2. A MeshForge license for `.inp` export

If the mesh completed but the button is still greyed, check the log panel for any quality worker errors.

### Exported `.inp` fails to import into Abaqus

Common causes:

- **`C3D4` instead of `C3D10` in the element block** — this should not happen in MeshForge v0.1, but if it does, report it as a bug with the STEP file attached
- **Abaqus version < 6.14** — C3D10 with midside nodes on curved edges requires Abaqus 6.14+
- **Node numbering starts at 0** — Abaqus requires 1-based node IDs; MeshForge outputs 1-based IDs but verify with a text editor if import fails

MeshForge exports geometry and connectivity only — no `*MATERIAL`, `*STEP`, or boundary conditions. Assign these in Abaqus/CAE after import.

### Export validation warning: "Line exceeds 80 characters"

Abaqus has an 80-character line limit for some keyword lines. This warning is non-fatal — modern Abaqus versions (2017+) accept longer lines. If you are using an older solver, contact support.

---

## License

### How does the license work?

Import, mesh, and quality review are **free with no element count cap**. Export to Abaqus `.inp` requires a paid license ($1,500/year per seat). Contact sibi.pianist@gmail.com to purchase.

### Can I evaluate export before buying?

Yes — the sample bracket geometry (`tests/fixtures/bracket_clean.step`) can be exported without a license for evaluation purposes. Production geometry requires a license.

### Does the license require internet access?

No. License validation is offline. The license file is installed locally and does not phone home.

---

## Reporting Bugs

Include the following in your bug report:

1. MeshForge version (Help → About)
2. OS and GPU
3. The STEP file (or a minimal reproduction)
4. The full log panel output (copy with right-click)
5. Steps to reproduce

[Open a bug report →](https://github.com/Storm-Raider/meshforge/issues/new)
