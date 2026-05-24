"""
Week 0 Task C — VTK 500k element render benchmark

Measures whether VTK 9 + PyQt6 can update scalar colors and re-render a 500k
element surface in under 500ms on the target hardware. This is the go/no-go
gate for the VTK rendering architecture.

Usage:
    python task_c_vtk_benchmark.py
    python task_c_vtk_benchmark.py --elements 500000   # default
    python task_c_vtk_benchmark.py --elements 100000   # quicker test pass

What it measures:
    1. vtkUnstructuredGrid construction time (once, not per-frame)
    2. vtkGeometryFilter surface extraction time (runs in QualityWorker)
    3. Scalar array assignment time (runs in QualityWorker)
    4. vtkPolyDataMapper + Render() time (runs in main thread — CRITICAL PATH)
    5. SetTableRange() + Render() time (quality filter interaction)

Pass criteria (from design doc):
    - vtkGeometryFilter + scalars: any time (runs in thread, not blocking)
    - Render() after scalar update: < 500ms
    - SetTableRange() + Render(): < 50ms (interactive filter)

If Render() > 500ms:
    → Check vtkOpenGLVertexBufferObjectGroup direct GPU upload path
    → If Python GIL is the bottleneck: C extension for scalar computation

Requirements (conda-forge only):
    conda install -c conda-forge vtk pyqt6
"""

import sys
import time
import argparse
import numpy as np

try:
    import vtk
    from vtk.util.numpy_support import numpy_to_vtkIdTypeArray, numpy_to_vtk
except ImportError:
    sys.exit("vtk not found. Run: conda install -c conda-forge vtk")

try:
    from PyQt6.QtWidgets import QApplication, QMainWindow
    from PyQt6.QtCore import QTimer
except ImportError:
    sys.exit("PyQt6 not found. Run: conda install -c conda-forge pyqt6")

try:
    from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
except ImportError:
    try:
        from vtk.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
    except ImportError:
        sys.exit("QVTKRenderWindowInteractor not found — check VTK + PyQt6 are both from conda-forge")


PASS_MS = 500
FILTER_MS = 50


def build_synthetic_tet_mesh(n_elements: int) -> vtk.vtkUnstructuredGrid:
    """
    Build a synthetic vtkUnstructuredGrid of n_elements C3D10 tets.
    Distributed on a unit sphere surface to approximate a real mesh.
    This is NOT Gmsh output — it's pure NumPy construction to test VTK overhead only.
    """
    print(f"Building synthetic mesh: {n_elements:,} C3D10 tets...")
    t0 = time.perf_counter()

    # Each C3D10 has 10 nodes; share nodes by building a grid
    # Simple approach: random tets in a cube (tests scalar pipeline, not geometry)
    rng = np.random.default_rng(42)

    # Approximate: 5-6 nodes per tet on average in a shared mesh
    n_nodes = max(int(n_elements * 0.6), 1000)

    # Node coordinates
    coords = rng.uniform(-1, 1, (n_nodes, 3)).astype(np.float32)

    # C3D10: 10 nodes per element
    # Use random node indices (not geometrically valid, but sufficient for pipeline timing)
    connectivity = rng.integers(0, n_nodes, size=(n_elements, 10))

    # Build vtkPoints
    points = vtk.vtkPoints()
    points.SetData(numpy_to_vtk(coords, deep=True))

    # Build vtkUnstructuredGrid
    grid = vtk.vtkUnstructuredGrid()
    grid.SetPoints(points)
    grid.Allocate(n_elements)

    # VTK_QUADRATIC_TETRA = 24 (C3D10)
    cell_type = vtk.VTK_QUADRATIC_TETRA
    for row in connectivity:
        id_list = vtk.vtkIdList()
        for nid in row:
            id_list.InsertNextId(int(nid))
        grid.InsertNextCell(cell_type, id_list)

    elapsed = time.perf_counter() - t0
    print(f"  Grid construction: {elapsed*1000:.0f}ms  ({n_nodes:,} nodes, {n_elements:,} elements)")
    return grid


def run_geometry_filter(grid: vtk.vtkUnstructuredGrid) -> vtk.vtkPolyData:
    """Extract surface polydata (runs in QualityWorker in production)."""
    print("\nRunning vtkGeometryFilter (surface extraction)...")
    t0 = time.perf_counter()

    geo = vtk.vtkGeometryFilter()
    geo.SetInputData(grid)
    geo.Update()
    surface = geo.GetOutput()

    elapsed = time.perf_counter() - t0
    n_cells = surface.GetNumberOfCells()
    print(f"  vtkGeometryFilter: {elapsed*1000:.0f}ms  ({n_cells:,} surface cells)")
    return surface


def build_scalar_array(n_cells: int) -> vtk.vtkFloatArray:
    """Build Jacobian scalar array (runs in QualityWorker in production)."""
    t0 = time.perf_counter()
    scalars_np = np.random.default_rng(0).uniform(0.0, 1.0, n_cells).astype(np.float32)
    scalars = numpy_to_vtk(scalars_np, deep=True)
    scalars.SetName("Jacobian")
    elapsed = time.perf_counter() - t0
    print(f"\n  Scalar array construction: {elapsed*1000:.0f}ms  ({n_cells:,} values)")
    return scalars, scalars_np


def build_lookup_table() -> vtk.vtkLookupTable:
    lut = vtk.vtkLookupTable()
    lut.SetNumberOfColors(256)
    lut.SetHueRange(0.667, 0.0)  # blue → red
    lut.SetTableRange(0.0, 1.0)
    lut.SetBelowRangeColor(0.5, 0.5, 0.5, 1.0)  # gray for filtered-out elements
    lut.SetUseBelowRangeColor(True)
    lut.Build()
    return lut


class BenchmarkWindow(QMainWindow):
    def __init__(self, n_elements: int):
        super().__init__()
        self.setWindowTitle(f"MeshForge VTK Benchmark — {n_elements:,} elements")
        self.resize(1280, 800)
        self.n_elements = n_elements
        self._results = {}

        # VTK widget
        self.vtk_widget = QVTKRenderWindowInteractor(self)
        self.setCentralWidget(self.vtk_widget)

        self.renderer = vtk.vtkRenderer()
        self.renderer.SetBackground(0.15, 0.15, 0.15)
        self.vtk_widget.GetRenderWindow().AddRenderer(self.renderer)

        # Run after window is shown
        QTimer.singleShot(200, self._run_benchmark)

    def _run_benchmark(self):
        print("\n" + "="*60)
        print(f"VTK RENDER BENCHMARK — {self.n_elements:,} C3D10 elements")
        print("="*60)

        # Build data (off-thread in production — timed here for reference only)
        grid = build_synthetic_tet_mesh(self.n_elements)
        surface = run_geometry_filter(grid)
        n_cells = surface.GetNumberOfCells()
        scalars, scalars_np = build_scalar_array(n_cells)
        lut = build_lookup_table()

        # Assign scalars to surface
        surface.GetCellData().SetScalars(scalars)
        surface.GetCellData().SetActiveScalars("Jacobian")

        # Build mapper (main thread — as in production)
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(surface)
        mapper.SetScalarModeToUseCellData()
        mapper.SetLookupTable(lut)
        mapper.SetScalarRange(0.0, 1.0)
        mapper.ScalarVisibilityOn()

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        self.renderer.AddActor(actor)
        self.renderer.ResetCamera()

        # ---- CRITICAL MEASUREMENT 1: First render after scalar assignment ----
        rw = self.vtk_widget.GetRenderWindow()
        rw.SetDesiredUpdateRate(30)

        print("\n[1] First Render() after scalar assignment (main thread)...")
        t0 = time.perf_counter()
        rw.Render()
        elapsed_render = (time.perf_counter() - t0) * 1000
        self._results["first_render_ms"] = elapsed_render
        status = "PASS" if elapsed_render < PASS_MS else "FAIL — investigate GPU upload path"
        print(f"    Render(): {elapsed_render:.0f}ms  [{status}]")

        # ---- CRITICAL MEASUREMENT 2: SetTableRange + Render (filter interaction) ----
        print("\n[2] SetTableRange() + Render() (quality filter interaction)...")
        timings = []
        ranges = [(0.0, 1.0), (0.0, 0.3), (0.1, 0.3), (0.3, 1.0), (0.0, 0.1)]
        for lo, hi in ranges:
            t0 = time.perf_counter()
            lut.SetTableRange(lo, hi)
            lut.Build()
            mapper.SetScalarRange(lo, hi)
            rw.Render()
            t = (time.perf_counter() - t0) * 1000
            timings.append(t)
            print(f"    Range [{lo:.1f}, {hi:.1f}]: {t:.0f}ms")

        mean_filter = np.mean(timings)
        self._results["filter_render_ms"] = mean_filter
        status = "PASS" if mean_filter < FILTER_MS else "WARN — filter interaction may feel sluggish"
        print(f"    Mean filter Render(): {mean_filter:.0f}ms  [{status}]")

        # ---- MEASUREMENT 3: Scalar update (simulate quality re-run) ----
        print("\n[3] Full scalar update + Render() (simulate quality re-run)...")
        new_scalars_np = np.random.default_rng(1).uniform(0.0, 1.0, n_cells).astype(np.float32)
        new_scalars = numpy_to_vtk(new_scalars_np, deep=True)
        new_scalars.SetName("Jacobian")

        t0 = time.perf_counter()
        surface.GetCellData().SetScalars(new_scalars)
        surface.GetCellData().Modified()
        surface.Modified()
        mapper.Update()
        rw.Render()
        elapsed_update = (time.perf_counter() - t0) * 1000
        self._results["scalar_update_ms"] = elapsed_update
        status = "PASS" if elapsed_update < PASS_MS else "FAIL"
        print(f"    Scalar update + Render(): {elapsed_update:.0f}ms  [{status}]")

        # ---- SUMMARY ----
        self._print_summary()
        QTimer.singleShot(3000, self.close)

    def _print_summary(self):
        r = self._results
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        print(f"  First render:    {r.get('first_render_ms', 0):.0f}ms  (pass < {PASS_MS}ms)")
        print(f"  Filter render:   {r.get('filter_render_ms', 0):.0f}ms  (pass < {FILTER_MS}ms)")
        print(f"  Scalar update:   {r.get('scalar_update_ms', 0):.0f}ms  (pass < {PASS_MS}ms)")

        all_pass = (
            r.get("first_render_ms", 9999) < PASS_MS
            and r.get("filter_render_ms", 9999) < FILTER_MS
            and r.get("scalar_update_ms", 9999) < PASS_MS
        )

        if all_pass:
            print("\n  RESULT: PASS — VTK architecture confirmed for this hardware.")
            print("  Proceed with T7 (VTK render pipeline) implementation.")
        else:
            print("\n  RESULT: FAIL — investigate before writing application code.")
            print("  Next steps:")
            if r.get("first_render_ms", 0) >= PASS_MS:
                print("    - First render slow: try vtkOpenGLVertexBufferObjectGroup direct GPU upload")
                print("    - Check GPU driver version and OpenGL version")
            if r.get("filter_render_ms", 0) >= FILTER_MS:
                print("    - Filter interaction slow: SetTableRange + Build() may be doing excess work")
                print("    - Try pre-building the LUT and only calling Modified() on the range")
            if r.get("scalar_update_ms", 0) >= PASS_MS:
                print("    - Scalar update slow: check if vtkFloatArray deep copy is bottleneck")
                print("    - Consider numpy_to_vtk with deep=False if data lifetime is controlled")


def main():
    parser = argparse.ArgumentParser(description="MeshForge Week 0 Task C — VTK benchmark")
    parser.add_argument("--elements", type=int, default=500_000, help="Number of synthetic C3D10 elements")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    win = BenchmarkWindow(args.elements)
    win.show()
    win.vtk_widget.Initialize()
    win.vtk_widget.Start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
