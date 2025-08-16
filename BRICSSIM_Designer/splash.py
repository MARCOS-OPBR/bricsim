from PyQt5.QtCore import QObject, QPropertyAnimation, Qt, QTimer, pyqtProperty
from PyQt5.QtGui import QPainter, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QWidget,
)


class OpacityWrapper(QObject):
    def __init__(self, item):
        super().__init__()
        self._item = item
        self._opacity = 0.0

    def get_opacity(self):
        return self._opacity

    def set_opacity(self, value):
        self._opacity = value
        self._item.setOpacity(value)

    opacity = pyqtProperty(float, get_opacity, set_opacity)


class SplashScreen(QWidget):
    def __init__(self, png_path, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.SplashScreen)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.view = QGraphicsView(self)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setStyleSheet("background: transparent; border: none;")
        self.scene = QGraphicsScene()
        self.view.setScene(self.scene)

        pixmap = QPixmap(png_path)
        self.logo_item = QGraphicsPixmapItem(pixmap)
        self.logo_item.setOpacity(0.0)
        self.scene.addItem(self.logo_item)

        self.wrapper = OpacityWrapper(self.logo_item)

        width = pixmap.width()
        height = pixmap.height()
        self.resize(width, height)
        self.view.setGeometry(0, 0, width, height)

        self.logo_item.setOffset(0, 0)

        # animação de fade-in
        self.animation = QPropertyAnimation(self.wrapper, b"opacity")
        self.animation.setDuration(1000)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.resize(width, height)
        self.view.setGeometry(0, 0, width, height)
        self.logo_item.setOffset(0, 0)

        # Centraliza splash na tela
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.center().x() - self.width() // 2
        y = screen.center().y() - self.height() // 2
        self.move(x, y)

        self.wrapper = OpacityWrapper(self.logo_item)

    def show_with_fade(self, callback):
        self.show()
        self.animation.finished.connect(
            lambda: QTimer.singleShot(500, lambda: self.finish(callback))
        )
        self.animation.start()

    def finish(self, callback):
        self.close()
        callback()
