from __future__ import annotations
import numpy as np

from PyQt6.QtCore import QThread, pyqtSignal

from meshforge.models.geometry_data import GeometryData
from meshforge.models.mesh_params import MeshParams


class SurfacePreviewWorker(QThread):
    """Generates a 2D surface mesh in a thread and converts it to vtkPolyData.

    Runs MeshEngine.surface_mesh() directly (no subprocess) — surface meshing
    takes seconds, making the subprocess overhead unnecessary. Uses _GMSH_LOCK
    internally so it cannot conflict with a running MeshWorker subprocess.
    """

    complete = pyqtSignal(object, int, int)  # vtkPolyData, tri_count, node_count
    failed = pyqtSignal(str)

    def __init__(self, geo: GeometryData, params: MeshParams | None = None, parent=None):
        super().__init__(parent)
        self._geo = geo
        self._params = params or MeshParams()

    def run(self) -> None:
        try:
            from meshforge.core.mesh_engine import MeshEngine
            mesh = MeshEngine(params=self._params).surface_mesh(self._geo)
            polydata = _mesh_to_polydata(mesh)
            tri_count = int(np.sum(mesh.element_types == 5))
            self.complete.emit(polydata, tri_count, mesh.node_count)
        except Exception as exc:
            self.failed.emit(str(exc))


def _mesh_to_polydata(mesh):
    """Convert a surface MeshData (triangles/quads) to vtkPolyData.

    Adds a "SurfaceTag" cell data array when mesh.surface_tags is populated,
    enabling per-surface picking and highlight in VtkViewer.
    """
    import vtk
    try:
        from vtk.util.numpy_support import numpy_to_vtk
    except ImportError:
        from vtkmodules.util.numpy_support import numpy_to_vtk

    pts = vtk.vtkPoints()
    pts.SetData(numpy_to_vtk(mesh.nodes.astype(np.float64), deep=True))

    polydata = vtk.vtkPolyData()
    polydata.SetPoints(pts)

    cells = vtk.vtkCellArray()
    cell_order: list[int] = []   # track which mesh element index each cell came from
    for i, conn in enumerate(mesh.connectivity):
        et = int(mesh.element_types[i])
        if et == 5:
            cells.InsertNextCell(3, conn[:3].astype(np.int64).tolist())
            cell_order.append(i)
        elif et == 9:
            cells.InsertNextCell(4, conn[:4].astype(np.int64).tolist())
            cell_order.append(i)
    polydata.SetPolys(cells)

    if len(mesh.surface_tags) == len(mesh.connectivity) and len(cell_order) > 0:
        tag_arr = vtk.vtkIntArray()
        tag_arr.SetName("SurfaceTag")
        tag_arr.SetNumberOfValues(len(cell_order))
        for cell_pos, elem_idx in enumerate(cell_order):
            tag_arr.SetValue(cell_pos, int(mesh.surface_tags[elem_idx]))
        polydata.GetCellData().AddArray(tag_arr)

    return polydata
