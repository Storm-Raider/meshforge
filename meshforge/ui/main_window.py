from __future__ import annotations
import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QStatusBar, QProgressBar, QPushButton,
    QFileDialog, QMessageBox, QApplication, QLabel,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QDesktopServices
from PyQt6.QtCore import QUrl

from meshforge.models.geometry_data import GeometryData
from meshforge.models.mesh_data import MeshData
from meshforge.workers.import_worker import ImportWorker
from meshforge.workers.mesh_worker import MeshWorker
from meshforge.workers.quality_worker import QualityWorker
from meshforge.export.inp_exporter import InpExporter
from meshforge.core.quality_engine import QualityEngine
from meshforge.ui.vtk_viewer import VtkViewer
from meshforge.ui.quality_panel import QualityPanel
from meshforge.ui.model_tree import ModelTree
from meshforge.ui.log_panel import LogPanel

import meshforge

# Application state machine states
_EMPTY = "empty"
_LOADING = "loading"
_SUCCESS = "success"
_PARTIAL = "partial"
_ERROR = "error"

_SAMPLE_STEP = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "bracket_clean.step"
_GITHUB_ISSUES = "https://github.com/Storm-Raider/meshforge/issues/new"
_DOCS_URL = "https://github.com/Storm-Raider/meshforge/blob/main/docs/getting-started.md"


class MainWindow(QMainWindow):
    """Top-level application window. Owns the state machine and all workers."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MeshForge")
        self.resize(1400, 900)

        self._state = _EMPTY
        self._geo: GeometryData | None = None
        self._mesh: MeshData | None = None
        self._import_worker: ImportWorker | None = None
        self._mesh_worker: MeshWorker | None = None
        self._quality_worker: QualityWorker | None = None
        self._current_file: str = ""

        self._build_ui()
        self._build_menu()
        self._apply_stylesheet()
        self._set_state(_EMPTY)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Three-panel horizontal splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._model_tree = ModelTree()
        splitter.addWidget(self._model_tree)

        self._vtk_viewer = VtkViewer()
        self._vtk_viewer.setAcceptDrops(True)
        self._vtk_viewer.dragEnterEvent = self._drag_enter
        self._vtk_viewer.dropEvent = self._drop_event
        splitter.addWidget(self._vtk_viewer)

        self._quality_panel = QualityPanel()
        self._quality_panel.threshold_changed.connect(self._vtk_viewer.set_threshold)
        splitter.addWidget(self._quality_panel)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([220, 900, 240])

        main_layout.addWidget(splitter, stretch=1)

        # Log panel at bottom
        self._log_panel = LogPanel()
        main_layout.addWidget(self._log_panel)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)  # indeterminate
        self._progress_bar.setMaximumWidth(200)
        self._progress_bar.hide()
        self._status_bar.addPermanentWidget(self._progress_bar)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFixedWidth(80)
        self._cancel_btn.hide()
        self._cancel_btn.clicked.connect(self._on_cancel)
        self._status_bar.addPermanentWidget(self._cancel_btn)

        # First-run sample geometry CTA (shown in empty state)
        self._sample_btn = QPushButton("Try with sample geometry")
        self._sample_btn.setFixedWidth(200)
        self._sample_btn.clicked.connect(self._load_sample)
        self._status_bar.addWidget(self._sample_btn)

    def _build_menu(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")
        open_action = QAction("Open STEP…", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_file_dialog)
        file_menu.addAction(open_action)

        file_menu.addSeparator()
        export_action = QAction("Export Abaqus .inp…", self)
        export_action.setShortcut("Ctrl+E")
        export_action.triggered.connect(self._export_inp)
        export_action.setEnabled(False)
        self._export_action = export_action
        file_menu.addAction(export_action)

        help_menu = menubar.addMenu("Help")

        docs_action = QAction("Documentation", self)
        docs_action.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(_DOCS_URL)))
        help_menu.addAction(docs_action)

        bug_action = QAction("Report a Bug", self)
        bug_action.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(_GITHUB_ISSUES)))
        help_menu.addAction(bug_action)

        help_menu.addSeparator()
        about_action = QAction("About MeshForge", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #1e1e1e; color: #ddd; }
            QSplitter::handle { background: #333; }
            QMenuBar { background-color: #252525; }
            QMenuBar::item:selected { background: #3a3a3a; }
            QMenu { background-color: #252525; }
            QMenu::item:selected { background: #3a3a3a; }
            QStatusBar { background: #252525; border-top: 1px solid #333; }
            QPushButton {
                background: #3a3a3a; border: 1px solid #555;
                padding: 4px 10px; border-radius: 3px;
            }
            QPushButton:hover { background: #4a4a4a; }
            QPushButton:disabled { color: #666; }
        """)

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def _set_state(self, state: str, message: str = "") -> None:
        self._state = state

        self._progress_bar.setVisible(state == _LOADING)
        self._cancel_btn.setVisible(state == _LOADING)
        self._sample_btn.setVisible(state == _EMPTY)
        self._export_action.setEnabled(state in (_SUCCESS, _PARTIAL))

        if state == _EMPTY:
            self._status_bar.showMessage("Drop a STEP file to begin, or click 'Try with sample geometry'.")
            self._vtk_viewer.show_empty_state()
            self._model_tree.clear()
            self._quality_panel.set_empty()

        elif state == _LOADING:
            self._status_bar.showMessage(message or "Loading…")
            self._cancel_btn.setText("Cancel")

        elif state == _SUCCESS:
            self._status_bar.showMessage(message or "Mesh ready.")

        elif state == _PARTIAL:
            self._status_bar.showMessage(message or "Mesh ready — some elements have low Jacobian quality.")

        elif state == _ERROR:
            self._status_bar.showMessage(f"Error: {message}")

    # ------------------------------------------------------------------
    # Import flow
    # ------------------------------------------------------------------

    def _open_file_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open STEP File", "", "STEP Files (*.step *.stp)"
        )
        if path:
            self._start_import(path)

    def _load_sample(self) -> None:
        if not _SAMPLE_STEP.exists():
            QMessageBox.warning(self, "Sample Not Found",
                                f"Sample geometry not found at:\n{_SAMPLE_STEP}\n\n"
                                "Run 'cp week0/component8.step tests/fixtures/bracket_clean.step' to install it.")
            return
        self._start_import(str(_SAMPLE_STEP))

    def _start_import(self, path: str) -> None:
        if self._state not in (_EMPTY, _SUCCESS, _PARTIAL, _ERROR):
            return

        if self._state in (_SUCCESS, _PARTIAL, _ERROR):
            reply = QMessageBox.question(
                self, "Replace current mesh?",
                "Replace the current mesh with a new import?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self._reset_state()

        self._current_file = path
        self._set_state(_LOADING, f"Importing {Path(path).name}…")
        self._log_panel.append(f"Importing: {path}")

        self._import_worker = ImportWorker(path, self)
        self._import_worker.complete.connect(self._on_import_complete)
        self._import_worker.failed.connect(self._on_import_failed)
        self._import_worker.start()

    def _on_import_complete(self, geo: GeometryData) -> None:
        self._geo = geo

        if not geo.is_valid():
            error_msg = geo.healing_status.replace("failed:", "").strip()
            QMessageBox.critical(self, "Geometry Validation Failed",
                                 f"Geometry validation failed.\n{error_msg}")
            self._set_state(_ERROR, "Geometry validation failed.")
            self._log_panel.append(f"Healing status: {geo.healing_status}", "error")
            return

        filename = Path(self._current_file).name
        self._model_tree.set_geometry(geo, filename)
        self._log_panel.append(
            f"Import OK: {geo.surface_count} surfaces, "
            f"bbox={geo.bounding_box_diagonal:.2f}, min_edge={geo.min_edge_length:.4f}"
        )

        # Auto-start meshing
        self._set_state(_LOADING, "Meshing…")
        self._mesh_worker = MeshWorker(geo, parent=self)
        self._mesh_worker.complete.connect(self._on_mesh_complete)
        self._mesh_worker.failed.connect(self._on_mesh_failed)
        self._mesh_worker.progress.connect(lambda msg: self._status_bar.showMessage(msg))
        self._mesh_worker.start()

    def _on_import_failed(self, error: str) -> None:
        QMessageBox.critical(self, "Import Failed", error)
        self._set_state(_ERROR, "Import failed.")
        self._log_panel.append(error, "error")

    def _on_mesh_complete(self, mesh: MeshData) -> None:
        try:
            if self._mesh_worker and self._mesh_worker.was_cancelled():
                self._reset_state()
                return

            self._mesh = mesh
            self._model_tree.set_mesh(mesh)
            self._log_panel.append(
                f"Mesh OK: {mesh.element_count:,} elements, {mesh.node_count:,} nodes"
            )

            self._set_state(_LOADING, "Computing quality…")
            self._quality_worker = QualityWorker(mesh, parent=self)
            self._quality_worker.scalars_ready.connect(self._on_quality_ready)
            self._quality_worker.failed.connect(self._on_quality_failed)
            self._quality_worker.start()
        except Exception as exc:
            import traceback
            self._log_panel.append(f"[BUG] _on_mesh_complete crashed: {exc}\n{traceback.format_exc()}", "error")
            self._set_state(_ERROR, f"Internal error: {exc}")

    def _on_mesh_failed(self, error: str, gmsh_log: list) -> None:
        QMessageBox.critical(self, "Meshing Failed", error)
        self._set_state(_ERROR, "Meshing failed.")
        self._log_panel.append(error, "error")
        if gmsh_log:
            self._log_panel.append_gmsh_log(gmsh_log)

    def _on_quality_ready(self, surface_polydata, quality_scalars) -> None:
        try:
            import numpy as np
            self._vtk_viewer.display_mesh(surface_polydata, quality_scalars)

            summary = QualityEngine().summary(quality_scalars)
            self._quality_panel.update_summary(summary)
            self._model_tree.set_quality(summary)

            state = _SUCCESS if summary["fail"] == 0 else _PARTIAL
            msg = (
                f"Mesh ready — {summary['element_count']:,} elements, "
                f"{summary['pass_pct']:.1f}% pass quality."
            )
            self._set_state(state, msg)
            self._log_panel.append(msg)
        except Exception as exc:
            import traceback
            self._log_panel.append(f"[BUG] _on_quality_ready crashed: {exc}\n{traceback.format_exc()}", "error")
            self._set_state(_ERROR, f"Internal error: {exc}")

    def _on_quality_failed(self, error: str) -> None:
        self._log_panel.append(error, "error")
        self._set_state(_ERROR, "Quality computation failed.")

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------

    def _on_cancel(self) -> None:
        if self._mesh_worker and self._mesh_worker.isRunning():
            self._mesh_worker.request_cancel()
            self._cancel_btn.setText("Cancelling…")
            self._cancel_btn.setEnabled(False)
        elif self._import_worker and self._import_worker.isRunning():
            # OCC has no interrupt — wait and discard
            self._cancel_btn.setText("Cancelling…")
            self._cancel_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _export_inp(self) -> None:
        if self._mesh is None or self._geo is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Abaqus .inp", "", "Abaqus Input (*.inp)"
        )
        if not path:
            return
        try:
            warnings = InpExporter().export(self._mesh, self._geo, path)
            if warnings:
                warn_text = "\n".join(f"• {w}" for w in warnings)
                QMessageBox.warning(self, "Export Warnings",
                                    f"Export completed with warnings:\n\n{warn_text}")
                self._log_panel.append(f"Export warnings: {warn_text}", "warn")
            else:
                self._log_panel.append(f"Exported: {path}")
                self._status_bar.showMessage(f"Exported to {Path(path).name}")
        except RuntimeError as e:
            QMessageBox.critical(self, "Export Failed", str(e))
            self._log_panel.append(str(e), "error")

    # ------------------------------------------------------------------
    # Drag and drop
    # ------------------------------------------------------------------

    def _drag_enter(self, event) -> None:
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and urls[0].toLocalFile().lower().endswith((".step", ".stp")):
                event.acceptProposedAction()

    def _drop_event(self, event) -> None:
        url = event.mimeData().urls()[0]
        self._start_import(url.toLocalFile())

    # ------------------------------------------------------------------
    # About dialog
    # ------------------------------------------------------------------

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About MeshForge",
            f"<b>MeshForge</b> v{meshforge.__version__}<br><br>"
            "Professional CAE meshing: STEP → C3D10 tet mesh → quality → Abaqus .inp<br><br>"
            "<b>Open source components:</b><br>"
            "• pythonocc-core (LGPL 2.1)<br>"
            "• Gmsh API (LGPL 2+)<br>"
            "• PyQt6 (LGPL 3)<br>"
            "• VTK 9 (Apache 2.0)<br><br>"
            "<i>macOS support planned for v1.1.</i>"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _reset_state(self) -> None:
        import gmsh
        try:
            gmsh.clear()
        except Exception:
            pass
        self._geo = None
        self._mesh = None
        self._current_file = ""
        self._set_state(_EMPTY)
