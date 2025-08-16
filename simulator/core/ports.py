from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable


@runtime_checkable
class DialogPort(Protocol):
    def info(self, title: str, msg: str) -> None: ...
    def warn(self, title: str, msg: str) -> None: ...


@runtime_checkable
class TimerPort(Protocol):
    def call_later(self, ms: int, fn: Callable[[], None]) -> None: ...
