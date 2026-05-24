from __future__ import annotations
from PyQt6.QtCore import QThread, pyqtSignal

from meshforge.core.step_importer import StepImporter
from meshforge.models.geometry_data import GeometryData


class ImportWorker(QThread):
    """Thin QThread wrapper around StepImporter.

    Emits complete(GeometryData) on success, failed(str) on error.
    One active ImportWorker at a time — caller enforces this.
    """

    complete = pyqtSignal(object)   # GeometryData
    failed = pyqtSignal(str)        # user-readable error message

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self._path = path

    def run(self) -> None:
        try:
            result = StepImporter().import_file(self._path)
            self.complete.emit(result)
        except Exception as e:
            self.failed.emit(str(e))
