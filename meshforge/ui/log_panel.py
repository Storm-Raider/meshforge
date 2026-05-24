from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout
from PyQt6.QtGui import QFont, QColor, QTextCharFormat, QTextCursor
from PyQt6.QtCore import Qt


class LogPanel(QWidget):
    """Bottom panel: collapsible log showing Gmsh output and app events."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        header = QHBoxLayout()
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setFixedWidth(60)
        self._clear_btn.clicked.connect(self.clear)
        header.addStretch()
        header.addWidget(self._clear_btn)
        layout.addLayout(header)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setFont(QFont("Monospace", 9))
        self._text.setMaximumHeight(140)
        layout.addWidget(self._text)

    def append(self, message: str, level: str = "info") -> None:
        """Append a log line. level: 'info' | 'warn' | 'error'."""
        fmt = QTextCharFormat()
        if level == "error":
            fmt.setForeground(QColor("#e03c3c"))
        elif level == "warn":
            fmt.setForeground(QColor("#f0a500"))
        else:
            fmt.setForeground(QColor("#cccccc"))

        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(message + "\n", fmt)
        self._text.setTextCursor(cursor)
        self._text.ensureCursorVisible()

    def append_gmsh_log(self, lines: list[str]) -> None:
        for line in lines:
            lower = line.lower()
            if "error" in lower:
                self.append(line, "error")
            elif "warning" in lower or "warn" in lower:
                self.append(line, "warn")
            else:
                self.append(line, "info")

    def clear(self) -> None:
        self._text.clear()
