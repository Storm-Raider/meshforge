from __future__ import annotations
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from meshforge.core.quality_engine import QualityEngine
from meshforge.models.mesh_data import MeshData


class QualityWorker(QThread):
    """Runs QualityEngine + vtkGeometryFilter off the main thread.

    Emits scalars_ready(surface_polydata, quality_scalars) when done.
    The main thread calls mapper.SetInputData / SetTableRange / Render only.
    """

    scalars_ready = pyqtSignal(object, object, object)  # (vtkPolyData, np.ndarray float32, vtkUnstructuredGrid)
    failed = pyqtSignal(str)

    def __init__(self, mesh: MeshData, parent=None):
        super().__init__(parent)
        self._mesh = mesh

    def run(self) -> None:
        try:
            import vtk
            from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray

            mesh = self._mesh

            # Build vtkUnstructuredGrid
            points = vtk.vtkPoints()
            coords_vtk = numpy_to_vtk(mesh.nodes.astype(np.float64), deep=True)
            points.SetData(coords_vtk)

            grid = vtk.vtkUnstructuredGrid()
            grid.SetPoints(points)
            grid.Allocate(mesh.element_count)

            for row in mesh.connectivity:
                id_list = vtk.vtkIdList()
                for nid in row:
                    id_list.InsertNextId(int(nid))
                grid.InsertNextCell(vtk.VTK_QUADRATIC_TETRA, id_list)

            # Compute quality scalars
            scalars_np = QualityEngine().compute(mesh)

            scalars_vtk = numpy_to_vtk(scalars_np, deep=True)
            scalars_vtk.SetName("Jacobian")
            grid.GetCellData().SetScalars(scalars_vtk)
            grid.GetCellData().SetActiveScalars("Jacobian")

            # Extract surface as linear triangles.
            # vtkGeometryFilter on C3D10 (quadratic tetra) produces VTK_QUADRATIC_TRIANGLE
            # cells which crash vtkRenderingOpenGL2 on some drivers.
            # vtkDataSetSurfaceFilter with NonlinearSubdivisionLevel=1 subdivides
            # quadratic faces into linear triangles before handing off to the renderer.
            surf_filter = vtk.vtkDataSetSurfaceFilter()
            surf_filter.SetInputData(grid)
            surf_filter.SetNonlinearSubdivisionLevel(1)
            surf_filter.Update()
            surface = surf_filter.GetOutput()

            self.scalars_ready.emit(surface, scalars_np, grid)

        except Exception as e:
            self.failed.emit(f"Quality computation failed: {e}")
