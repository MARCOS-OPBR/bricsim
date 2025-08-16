from __future__ import annotations
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtCore import QTimer

from simulator.core.ports import DialogPort, TimerPort

class QtDialogs(DialogPort):
    def __init__(self, parent=None):
        self.parent = parent
    def info(self, title: str, msg: str) -> None:
        QMessageBox.information(self.parent, title, msg)
    def warn(self, title: str, msg: str) -> None:
        QMessageBox.warning(self.parent, title, msg)

class QtTimer(TimerPort):
    def call_later(self, ms: int, fn):
        QTimer.singleShot(ms, fn)
