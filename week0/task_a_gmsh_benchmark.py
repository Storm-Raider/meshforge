"""
Week 0 Task A — Gmsh Algorithm3D benchmark: Delaunay (1) vs. HXT (9)

Usage:
    python task_a_gmsh_benchmark.py path/to/your_part.step

What it does:
    1. Imports the STEP file via Gmsh
    2. Meshes twice: once with Algorithm3D=1 (Delaunay) and once with Algorithm3D=9 (HXT)
    3. Computes scaled Jacobian for every C3D10 element using the same NumPy formula
       that MeshForge will use in production
    4. Prints a side-by-side quality summary (min, mean, % pass/warn/fail)
    5. Saves both meshes as .msh files and exports .inp files for Abaqus round-trip (Task E)
    6. Writes a histogram PNG so you can paste it into your notes

Requirements (conda-forge only):
    conda install -c conda-forge gmsh numpy matplotlib

Decision rule after running:
    - If HXT mean Jacobian > Delaunay mean Jacobian AND HXT runtime < 2x Delaunay: choose HXT (Algorithm3D=9)
    - If HXT fails or produces significantly more warn/fail elements: choose Delaunay (Algorithm3D=1)
    - Update the meshing spec in the design doc with the winner.
"""

import sys
import time
import numpy as np

try:
    import gmsh
except ImportError:
    sys.exit("gmsh not found. Run: conda install -c conda-forge gmsh")

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("matplotlib not found — histogram PNG will be skipped. Run: conda install -c conda-forge matplotlib")


PASS_THRESHOLD = 0.3
WARN_THRESHOLD = 0.1

# Surface mesh: Frontal-Delaunay (Algorithm 6) — locked choice from design doc
SURFACE_ALGO = 6

# Global element size: 3% of bounding box diagonal (MeshForge default formula)
# Override with --size-factor if the geometry needs coarser/finer mesh
SIZE_FACTOR = 0.03


def init_gmsh(verbose: bool = False):
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 1 if verbose else 0)
    gmsh.option.setNumber("General.Verbosity", 3 if verbose else 1)


def load_step(path: str) -> tuple[float, float]:
    """Import STEP, apply OCC healing, return (bbox_diagonal, min_edge_length)."""
    gmsh.model.add("meshforge_benchmark")
    gmsh.model.occ.importShapes(path)
    gmsh.model.occ.healShapes()
    gmsh.model.occ.synchronize()

    bbox = gmsh.model.getBoundingBox(-1, -1)
    dx = bbox[3] - bbox[0]
    dy = bbox[4] - bbox[1]
    dz = bbox[5] - bbox[2]
    diagonal = (dx**2 + dy**2 + dz**2) ** 0.5

    # Approximate min edge length from 1D entities
    curves = gmsh.model.getEntities(1)
    lengths = []
    for _, tag in curves:
        pts = gmsh.model.mesh.getNodes(1, tag, includeBoundary=True)[1]
        if len(pts) >= 6:
            p0 = np.array(pts[:3])
            p1 = np.array(pts[3:6])
            lengths.append(np.linalg.norm(p1 - p0))
    min_edge = min(lengths) if lengths else diagonal * 0.01

    return diagonal, min_edge


def set_mesh_params(diagonal: float, min_edge: float):
    """Apply MeshForge default sizing (matches production formula)."""
    target_size = min(SIZE_FACTOR * diagonal, 0.5 * min_edge)
    gmsh.option.setNumber("Mesh.CharacteristicLengthMin", target_size * 0.5)
    gmsh.option.setNumber("Mesh.CharacteristicLengthMax", target_size * 2.0)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 12)
    gmsh.option.setNumber("Mesh.Algorithm", SURFACE_ALGO)
    try:
        gmsh.option.setNumber("Mesh.SecondOrderOptimize", 1)
    except Exception:
        pass  # renamed in gmsh 4.14+; optimization still runs via setOrder(2)


def run_mesh(algorithm3d: int) -> tuple[float, np.ndarray]:
    """
    Mesh volume with given Algorithm3D, set second-order (C3D10).
    Returns (elapsed_seconds, jacobian_array).
    """
    gmsh.option.setNumber("Mesh.Algorithm3D", algorithm3d)

    t0 = time.perf_counter()
    gmsh.model.mesh.generate(3)
    gmsh.model.mesh.setOrder(2)
    elapsed = time.perf_counter() - t0

    jacobians = compute_jacobians()
    return elapsed, jacobians


def compute_jacobians() -> np.ndarray:
    """
    Vectorised scaled Jacobian computation using the MeshForge production formula.
    Uses first 4 corner nodes of each C3D10 element (same as QualityEngine will).
    """
    elem_types, elem_tags, node_tags_flat = gmsh.model.mesh.getElements(3)

    if not elem_types:
        return np.array([])

    # Fetch all node coordinates in one call — O(1) round-trips to gmsh
    all_node_tags, all_coords, _ = gmsh.model.mesh.getNodes()
    coord_array = np.array(all_coords, dtype=np.float64).reshape(-1, 3)
    tag_to_idx = {int(t): i for i, t in enumerate(all_node_tags)}

    all_jac = []

    for etype, etags, ntags in zip(elem_types, elem_tags, node_tags_flat):
        props = gmsh.model.mesh.getElementProperties(etype)
        nodes_per_elem = props[3]

        if nodes_per_elem < 4:
            continue

        ntags_arr = np.array(ntags, dtype=np.int64).reshape(-1, nodes_per_elem)

        # Map corner node tags → coordinate array indices (vectorised)
        corner_tags = ntags_arr[:, :4]
        corner_indices = np.array([[tag_to_idx[int(t)] for t in row] for row in corner_tags])
        corner_coords = coord_array[corner_indices]  # (n_elem, 4, 3)

        # Build Jacobian matrices: J[i] = [v1-v0, v2-v0, v3-v0]
        v0 = corner_coords[:, 0, :]
        v1 = corner_coords[:, 1, :]
        v2 = corner_coords[:, 2, :]
        v3 = corner_coords[:, 3, :]
        J = np.stack([v1 - v0, v2 - v0, v3 - v0], axis=-1)  # (N, 3, 3)

        det_J = np.linalg.det(J)
        # Correct scaled Jacobian: det(J) / (||col0|| * ||col1|| * ||col2||)
        # J shape: (N, 3, 3); norm along axis=1 gives (N, 3) column norms
        col_norms = np.linalg.norm(J, axis=1)          # (N, 3)
        col_norm_product = col_norms[:, 0] * col_norms[:, 1] * col_norms[:, 2]  # (N,)
        denom = np.where(col_norm_product < 1e-12, 1e-12, col_norm_product)
        scaled_jac = det_J / denom
        all_jac.append(scaled_jac)

    if not all_jac:
        return np.array([])
    return np.concatenate(all_jac)


def quality_summary(jac: np.ndarray, label: str, elapsed: float):
    if len(jac) == 0:
        print(f"  {label}: NO ELEMENTS — mesh likely failed")
        return

    n = len(jac)
    n_pass = np.sum(jac > PASS_THRESHOLD)
    n_warn = np.sum((jac >= WARN_THRESHOLD) & (jac <= PASS_THRESHOLD))
    n_fail = np.sum(jac < WARN_THRESHOLD)

    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  Elements:   {n:,}")
    print(f"  Time:       {elapsed:.1f}s")
    print(f"  Min Jac:    {jac.min():.4f}")
    print(f"  Mean Jac:   {jac.mean():.4f}")
    print(f"  Max Jac:    {jac.max():.4f}")
    print(f"  Pass (>0.3): {n_pass:,}  ({100*n_pass/n:.1f}%)")
    print(f"  Warn (0.1-0.3): {n_warn:,}  ({100*n_warn/n:.1f}%)")
    print(f"  Fail (<0.1): {n_fail:,}  ({100*n_fail/n:.1f}%)")


def save_results(step_path: str, algo: int, jac: np.ndarray, elapsed: float):
    label = "delaunay" if algo == 1 else "hxt"
    base = step_path.rsplit(".", 1)[0]

    msh_path = f"{base}_{label}.msh"
    inp_path = f"{base}_{label}.inp"

    gmsh.write(msh_path)
    gmsh.write(inp_path)
    print(f"  Saved: {msh_path}")
    print(f"  Saved: {inp_path}  ← use this for Task E Abaqus round-trip")

    return jac


def plot_comparison(jac1: np.ndarray, jac2: np.ndarray, out_path: str):
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    fig.suptitle("Scaled Jacobian Distribution — Algorithm3D 1 (Delaunay) vs. 9 (HXT)", fontsize=13)

    for ax, jac, title in zip(axes, [jac1, jac2], ["Algorithm3D=1 (Delaunay)", "Algorithm3D=9 (HXT)"]):
        ax.hist(jac, bins=50, color="#4c8cbf", edgecolor="white", linewidth=0.3)
        ax.axvline(PASS_THRESHOLD, color="#e03c3c", linestyle="--", label=f"Pass threshold ({PASS_THRESHOLD})")
        ax.axvline(WARN_THRESHOLD, color="#f0a500", linestyle="--", label=f"Warn threshold ({WARN_THRESHOLD})")
        ax.set_title(title)
        ax.set_xlabel("Scaled Jacobian")
        ax.set_ylabel("Element count")
        ax.legend(fontsize=8)

    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    print(f"\n  Histogram saved: {out_path}")


def benchmark(step_path: str):
    results = {}

    for algo, label in [(1, "Algorithm3D=1 (Delaunay)"), (9, "Algorithm3D=9 (HXT)")]:
        print(f"\nRunning {label}...")
        init_gmsh(verbose=False)

        try:
            diagonal, min_edge = load_step(step_path)
            set_mesh_params(diagonal, min_edge)
            elapsed, jac = run_mesh(algo)
            quality_summary(jac, label, elapsed)
            save_results(step_path, algo, jac, elapsed)
            results[algo] = (elapsed, jac)
        except Exception as e:
            print(f"  FAILED: {e}")
            results[algo] = (0, np.array([]))
        finally:
            gmsh.finalize()

    # Comparison
    jac1 = results.get(1, (0, np.array([])))[1]
    jac2 = results.get(9, (0, np.array([])))[1]

    if len(jac1) > 0 and len(jac2) > 0:
        print(f"\n{'='*60}")
        print("  DECISION SUMMARY")
        print(f"{'='*60}")
        mean1, mean2 = jac1.mean(), jac2.mean()
        t1, t2 = results[1][0], results[9][0]
        print(f"  Delaunay: mean Jac={mean1:.4f}, time={t1:.1f}s")
        print(f"  HXT:      mean Jac={mean2:.4f}, time={t2:.1f}s")

        if mean2 > mean1 and t2 < t1 * 2:
            print("  → RECOMMENDATION: HXT (Algorithm3D=9) — better quality, acceptable speed")
        elif mean2 > mean1:
            print("  → RECOMMENDATION: HXT (Algorithm3D=9) — better quality despite slower runtime")
        else:
            print("  → RECOMMENDATION: Delaunay (Algorithm3D=1) — better quality for this geometry class")

        print("\n  Update the meshing spec in the design doc with the winner before writing application code.")

        if HAS_MATPLOTLIB:
            hist_path = step_path.rsplit(".", 1)[0] + "_jacobian_comparison.png"
            plot_comparison(jac1, jac2, hist_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python task_a_gmsh_benchmark.py path/to/part.step")

    step_path = sys.argv[1]
    print(f"\nMeshForge Week 0 — Task A: Algorithm3D Benchmark")
    print(f"STEP file: {step_path}\n")
    benchmark(step_path)
