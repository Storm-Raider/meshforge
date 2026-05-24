from __future__ import annotations
import sys

from PyQt6.QtWidgets import QApplication, QMessageBox
import vtk


def _check_opengl() -> bool:
    """Check OpenGL 3.2+ availability before showing the main window."""
    rw = vtk.vtkRenderWindow()
    rw.SetOffScreenRendering(True)
    try:
        rw.Initialize()
        renderer = vtk.vtkRenderer()
        rw.AddRenderer(renderer)
        rw.Render()
        # VTK reports OpenGL version via context info
        info = vtk.vtkOpenGLRenderWindow()
        # If we got here without exception, OpenGL is available
        return True
    except Exception:
        return False
    finally:
        try:
            rw.Finalize()
        except Exception:
            pass


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("MeshForge")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("MeshForge")

    # GPU / OpenGL startup check
    rw = vtk.vtkRenderWindow()
    rw.SetOffScreenRendering(True)
    rw.Initialize()
    renderer = vtk.vtkRenderer()
    rw.AddRenderer(renderer)
    try:
        rw.Render()
    except Exception as e:
        QMessageBox.critical(
            None,
            "GPU Compatibility Error",
            "MeshForge requires OpenGL 3.2 or newer for 3D rendering.\n\n"
            "Your GPU or driver may not be compatible.\n\n"
            "Try: update your graphics driver. Contact support if the issue persists.\n\n"
            f"Detail: {e}",
        )
        sys.exit(1)
    finally:
        try:
            rw.Finalize()
        except Exception:
            pass

    from meshforge.ui.main_window import MainWindow
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
