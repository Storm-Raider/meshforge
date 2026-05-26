# Getting Started with MeshForge

MeshForge converts STEP files to C3D10 quadratic tetrahedral meshes with Jacobian quality visualization and Abaqus `.inp` export.

---

## System Requirements

| Component | Minimum |
|---|---|
| OS | Windows 10 64-bit, Ubuntu 22.04 |
| GPU | OpenGL 3.2 (any discrete GPU from 2012+; Intel HD 4000+) |
| RAM | 8 GB (16 GB recommended for assemblies >500k elements) |
| Disk | 4 GB (conda environment) |

> **Note:** Integrated graphics work but VTK viewport performance degrades above ~200k elements. A dedicated GPU is recommended for production use.

---

## Installation

### Developer / beta install (conda)

```bash
git clone https://github.com/Storm-Raider/meshforge.git
cd meshforge
conda env create -f environment.yml
conda activate meshforge
pip install -e .
meshforge
```

### Verify the install

```bash
pytest          # all tests should pass
meshforge       # launches the application
```

---

## Quick Start: Mesh the Sample Bracket

The fastest way to confirm everything works is to mesh the bundled bracket geometry.

1. Launch MeshForge: `meshforge` (or double-click the desktop shortcut)
2. In the empty viewport, click **"Try with sample geometry"**
3. MeshForge imports `bracket_clean.step` and begins meshing automatically
4. When meshing completes (~15–60 s depending on hardware), the viewport shows the surface mesh colored by Jacobian quality
5. Review the **Quality** panel on the right — a clean geometry like the bracket should show >95% pass (green bar)
6. Click **Export .inp** to save an Abaqus input file

---

## Loading Your Own Geometry

**Drag and drop** a `.step` or `.stp` file onto the viewport, or use **File → Open**.

MeshForge accepts:
- STEP AP203 and AP214 (single solid, shell, or assembly)
- One file at a time (multi-body assembly support in v2)

After import, the **Model** panel shows:
- Surface count
- Bounding box diagonal
- Minimum edge length
- Healing status (`ok`, `warn: <detail>`, or `failed: <detail>`)

If healing status shows `warn`, the mesh will still proceed — MeshForge tolerates minor gaps and non-manifold edges. A `failed` status means OCC could not produce a watertight solid; meshing is blocked and the log panel shows the reason.

---

## Mesh Size Controls

The **size factor** slider (top toolbar) scales the global element size:

| Setting | Effect |
|---|---|
| 1.0 (default) | ~3% of bounding box diagonal, limited by 50% of min edge |
| 0.5 | Finer — 2× more elements, ~4× longer mesh time |
| 2.0 | Coarser — faster for geometry validation, not for analysis |

For thin-walled parts, increase the size factor if meshing fails with "edge recovery" errors — very small elements cannot be created conformally near thin features.

---

## Understanding Quality Colors

The viewport uses a **blue → red** color scale for scaled Jacobian quality:

| Color | Jacobian range | Meaning |
|---|---|---|
| Blue | > 0.3 | Pass — suitable for implicit FEA |
| Yellow/Orange | 0.1 – 0.3 | Warn — acceptable for linear static, marginal for nonlinear |
| Red | < 0.1 | Fail — element may cause solver convergence issues |
| Gray | (filtered out) | Below the viewport threshold slider |

The **Quality** panel shows element counts and percentages for each band, plus min/mean/max Jacobian.

A mesh ready for production Abaqus analysis should show:
- Pass % > 90%
- No fail elements, or < 0.1% fail with min Jacobian > 0.05
- Mean Jacobian > 0.5

---

## Exporting to Abaqus

Click **Export .inp** (requires a license for production use — see below).

The exported file contains:
- `*NODE` block — all nodes with 1-based IDs
- `*ELEMENT, TYPE=C3D10` block — 10-node quadratic tetrahedra
- No `*MATERIAL`, `*STEP`, or boundary conditions — MeshForge exports geometry and connectivity only

Import into Abaqus/CAE via **File → Import → Input File**, then assign materials and boundary conditions in the usual workflow.

> **License:** Import, mesh, and quality review are free. Export to `.inp` requires a MeshForge license ($1,500/year). Contact sibi.pianist@gmail.com to purchase.

---

## Cancelling a Mesh

Click **Cancel** during meshing. The button label changes to **"Cancelling… (waiting for Gmsh)"** — MeshForge waits for the current Gmsh operation to finish before discarding the result. On large geometries this may take up to 30 seconds.

---

## Troubleshooting

### "Self-intersecting surface detected near surface N"
The geometry has overlapping faces. In your CAD tool: check for duplicate bodies, zero-thickness walls, or self-intersecting sweeps near the reported surface. Increase the size factor as a workaround — larger elements may bridge the intersection.

### "Could not create a conforming mesh near surface N"
The mesh cannot conform to a very thin feature. Increase the size factor to 5% or larger, or suppress the thin feature in CAD if it is not structurally significant.

### "Gmsh produced no 3D elements"
OCC returned an open shell that Gmsh cannot volume-mesh. Check the model tree — if healing status shows `failed`, the STEP file has a non-manifold or open topology that could not be closed. Re-export from CAD as a solid body.

### "OpenGL 3.2 not available"
MeshForge requires OpenGL 3.2 for the VTK viewport. On Windows, update your GPU driver. On a headless server or VM, ensure hardware GPU passthrough is enabled. Software rendering (Mesa) is not supported.

### Export button is greyed out
Export requires a valid mesh. Complete the meshing step first. If export is still greyed out after a successful mesh, check that the mesh has at least one element in the Quality panel.

---

## Next Steps

- [FAQ and Troubleshooting](faq.md) — full list of error messages and fixes
- [Changelog](changelog.md) — version history
- [Report a bug](https://github.com/Storm-Raider/meshforge/issues/new)
