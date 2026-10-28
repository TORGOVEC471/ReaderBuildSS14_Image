from PyQt6.QtWidgets import (
    QLabel
)
from PyQt6.QtCore import Qt, pyqtSignal

# Кликабельный QLabel
class ClickableLabel(QLabel):
    """Специальный QLabel, который умеет излучать сигнал clicked при нажатии."""
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)