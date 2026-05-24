from __future__ import annotations
import numpy as np

import vtk
from vtk.util.numpy_support import numpy_to_vtk

try:
    from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
except ImportError:
    from vtk.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt


class VtkViewer(QWidget):
    """Centre viewport: VTK OpenGL render window embedded in PyQt6.

    Main thread only after construction. All slow operations (geometry filter,
    scalar computation) happen in workers; this class receives ready-to-render
    surface polydata and scalars and calls Render().
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._build_vtk_pipeline()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._vtk_widget = QVTKRenderWindowInteractor(self)
        layout.addWidget(self._vtk_widget)

        # Empty-state overlay — hidden once a mesh is loaded
        self._empty_label = QLabel(
            "Drop a STEP file here to import\n— or —"
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(
            "color: #888; font-size: 16px; background: transparent;"
        )
        self._empty_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self._empty_label)

    def _build_vtk_pipeline(self) -> None:
        self._renderer = vtk.vtkRenderer()
        self._renderer.SetBackground(0.15, 0.15, 0.15)

        rw = self._vtk_widget.GetRenderWindow()
        rw.AddRenderer(self._renderer)
        self._vtk_widget.Initialize()

        self._lut = self._build_lut()
        self._mapper = vtk.vtkPolyDataMapper()
        self._mapper.SetLookupTable(self._lut)
        self._mapper.SetScalarModeToUseCellData()
        self._mapper.ScalarVisibilityOn()
        self._mapper.SetScalarRange(0.0, 1.0)

        self._actor = vtk.vtkActor()
        self._actor.SetMapper(self._mapper)
        self._actor.SetVisibility(False)
        self._renderer.AddActor(self._actor)

        style = vtk.vtkInteractorStyleTrackballCamera()
        self._vtk_widget.GetRenderWindow().GetInteractor().SetInteractorStyle(style)

    def _build_lut(self) -> vtk.vtkLookupTable:
        lut = vtk.vtkLookupTable()
        lut.SetNumberOfColors(256)
        lut.SetHueRange(0.667, 0.0)   # blue (good) → red (bad)
        lut.SetTableRange(0.0, 1.0)
        lut.SetBelowRangeColor(0.4, 0.4, 0.4, 1.0)  # gray for filtered elements
        lut.SetUseBelowRangeColor(True)
        lut.Build()
        return lut

    def display_mesh(self, surface_polydata, quality_scalars: np.ndarray) -> None:
        """Called from main thread after QualityWorker emits scalars_ready."""
        scalars_vtk = numpy_to_vtk(quality_scalars, deep=True)
        scalars_vtk.SetName("Jacobian")
        surface_polydata.GetCellData().SetScalars(scalars_vtk)
        surface_polydata.GetCellData().SetActiveScalars("Jacobian")

        self._mapper.SetInputData(surface_polydata)
        self._mapper.SetScalarRange(0.0, 1.0)
        self._lut.SetTableRange(0.0, 1.0)
        self._actor.SetVisibility(True)
        self._renderer.ResetCamera()

        self._empty_label.hide()
        self._vtk_widget.GetRenderWindow().Render()

    def set_threshold(self, lo: float, hi: float) -> None:
        """Update quality filter — called from QualityPanel.threshold_changed signal."""
        self._lut.SetTableRange(lo, hi)
        self._lut.Build()
        self._mapper.SetScalarRange(lo, hi)
        self._vtk_widget.GetRenderWindow().Render()

    def clear(self) -> None:
        self._actor.SetVisibility(False)
        self._renderer.ResetCamera()
        self._vtk_widget.GetRenderWindow().Render()
        self._empty_label.show()

    def show_empty_state(self) -> None:
        self.clear()
