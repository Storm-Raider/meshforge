from __future__ import annotations
import numpy as np

import vtk

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
        # Disable MSAA and alpha bits — avoids access violation in vtkRenderingOpenGL2
        # when the Qt6 OpenGL context doesn't expose the default sample/alpha config.
        rw.SetMultiSamples(0)
        rw.SetAlphaBitPlanes(0)
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

        # Isolate pipeline: 3D grid → threshold (≤0.3) → surface extract → actor
        self._grid = None
        self._isolate_threshold = vtk.vtkThreshold()
        self._isolate_threshold.SetInputArrayToProcess(
            0, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_CELLS, "Jacobian"
        )
        # Keep cells where Jacobian ≤ 0.3 (non-passing: warn + fail)
        self._isolate_threshold.SetLowerThreshold(0.3)
        self._isolate_threshold.SetThresholdFunction(
            vtk.vtkThreshold.THRESHOLD_LOWER
        )

        self._isolate_surf = vtk.vtkDataSetSurfaceFilter()
        self._isolate_surf.SetInputConnection(self._isolate_threshold.GetOutputPort())
        self._isolate_surf.SetNonlinearSubdivisionLevel(1)

        self._isolate_mapper = vtk.vtkPolyDataMapper()
        self._isolate_mapper.SetInputConnection(self._isolate_surf.GetOutputPort())
        self._isolate_mapper.SetLookupTable(self._lut)
        self._isolate_mapper.SetScalarModeToUseCellData()
        self._isolate_mapper.ScalarVisibilityOn()
        self._isolate_mapper.SetScalarRange(0.0, 1.0)

        self._isolate_actor = vtk.vtkActor()
        self._isolate_actor.SetMapper(self._isolate_mapper)
        self._isolate_actor.SetVisibility(False)
        self._renderer.AddActor(self._isolate_actor)

        # Scalar bar (color legend) — shown when mesh is loaded
        self._scalar_bar = vtk.vtkScalarBarActor()
        self._scalar_bar.SetLookupTable(self._lut)
        self._scalar_bar.SetTitle("Jacobian")
        self._scalar_bar.SetNumberOfLabels(5)
        self._scalar_bar.SetOrientationToVertical()
        self._scalar_bar.SetWidth(0.07)
        self._scalar_bar.SetHeight(0.38)
        self._scalar_bar.GetPositionCoordinate().SetCoordinateSystemToNormalizedDisplay()
        self._scalar_bar.GetPositionCoordinate().SetValue(0.905, 0.08)
        for prop in (self._scalar_bar.GetTitleTextProperty(),
                     self._scalar_bar.GetLabelTextProperty()):
            prop.SetColor(0.8, 0.8, 0.8)
            prop.SetFontSize(10)
            prop.BoldOff()
            prop.ItalicOff()
            prop.ShadowOff()
        self._scalar_bar.SetVisibility(False)
        self._renderer.AddActor2D(self._scalar_bar)

        style = vtk.vtkInteractorStyleTrackballCamera()
        interactor = self._vtk_widget.GetRenderWindow().GetInteractor()
        interactor.SetInteractorStyle(style)
        interactor.AddObserver("KeyPressEvent", self._on_key_press)

    def _build_lut(self) -> vtk.vtkLookupTable:
        lut = vtk.vtkLookupTable()
        lut.SetNumberOfColors(256)
        lut.SetHueRange(0.667, 0.0)   # blue (good) → red (bad)
        lut.SetTableRange(0.0, 1.0)
        lut.SetBelowRangeColor(0.4, 0.4, 0.4, 1.0)  # gray for filtered elements
        lut.SetUseBelowRangeColor(True)
        lut.Build()
        return lut

    def display_mesh(self, surface_polydata, quality_scalars: np.ndarray, grid) -> None:
        """Called from main thread after QualityWorker emits scalars_ready.

        surface_polydata already carries per-surface-cell Jacobian scalars
        set by QualityWorker (mapped from the 3D grid).  Do NOT reassign
        quality_scalars (per-3D-element) here — surface has more cells than
        3D elements, causing an out-of-bounds read in vtkRenderingOpenGL2.
        """
        self._grid = grid
        self._isolate_threshold.SetInputData(grid)

        # Reset to normal view; isolate toggle restores itself via set_isolate_failures
        self._mapper.SetInputData(surface_polydata)
        self._mapper.SetScalarRange(0.0, 1.0)
        self._lut.SetTableRange(0.0, 1.0)
        self._actor.SetVisibility(True)
        self._isolate_actor.SetVisibility(False)
        self._scalar_bar.SetVisibility(True)
        self._renderer.ResetCamera()

        self._empty_label.hide()
        self._vtk_widget.GetRenderWindow().Render()

    def set_threshold(self, lo: float, hi: float) -> None:
        """Update quality filter — called from QualityPanel.threshold_changed signal."""
        self._lut.SetTableRange(lo, hi)
        self._lut.Build()
        self._mapper.SetScalarRange(lo, hi)
        self._isolate_mapper.SetScalarRange(lo, hi)
        self._vtk_widget.GetRenderWindow().Render()

    def set_isolate_failures(self, enabled: bool) -> None:
        """Toggle geometric isolation of non-passing elements (Jacobian ≤ 0.3)."""
        if enabled and self._grid is not None:
            self._actor.SetVisibility(False)
            self._isolate_actor.SetVisibility(True)
        else:
            self._actor.SetVisibility(self._grid is not None)
            self._isolate_actor.SetVisibility(False)
        self._vtk_widget.GetRenderWindow().Render()

    def clear(self) -> None:
        self._grid = None
        self._actor.SetVisibility(False)
        self._isolate_actor.SetVisibility(False)
        self._scalar_bar.SetVisibility(False)
        self._renderer.ResetCamera()
        self._vtk_widget.GetRenderWindow().Render()
        self._empty_label.show()

    def show_empty_state(self) -> None:
        self.clear()

    def _on_key_press(self, obj, event) -> None:
        key = obj.GetKeySym()
        if key in ("f", "F"):
            self._renderer.ResetCamera()
            self._vtk_widget.GetRenderWindow().Render()
        elif key in ("1", "KP_1"):
            self._set_standard_view((0, -1, 0), (0, 0, 1))
        elif key in ("3", "KP_3"):
            self._set_standard_view((1, 0, 0), (0, 0, 1))
        elif key in ("7", "KP_7"):
            self._set_standard_view((0, 0, 1), (0, 1, 0))

    def _set_standard_view(self, pos_dir: tuple, up_dir: tuple) -> None:
        cam = self._renderer.GetActiveCamera()
        fp = cam.GetFocalPoint()
        dist = cam.GetDistance()
        cam.SetPosition(
            fp[0] + pos_dir[0] * dist,
            fp[1] + pos_dir[1] * dist,
            fp[2] + pos_dir[2] * dist,
        )
        cam.SetViewUp(*up_dir)
        self._renderer.ResetCameraClippingRange()
        self._vtk_widget.GetRenderWindow().Render()
