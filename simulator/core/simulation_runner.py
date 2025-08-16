# simulator/core/simulation_runner.py
from __future__ import annotations

from .ports import DialogPort, TimerPort


class SimulationRunner:
    def __init__(self, dialogs: DialogPort, timer: TimerPort):
        self.dialogs = dialogs
        self.timer = timer

    def start(self):
        self.dialogs.info("Simulação", "Iniciando...")
        self.timer.call_later(100, self._tick)

    def _tick(self): ...
