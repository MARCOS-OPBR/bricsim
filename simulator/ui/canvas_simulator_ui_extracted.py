"""
Shim de compatibilidade: módulo movido para design.ui.canvas_simulator.
Este arquivo será depreciado em versões futuras.
"""
from warnings import warn as _warn
_warn("Módulo movido para design.ui.canvas_simulator", DeprecationWarning, stacklevel=2)
from design.ui.canvas_simulator import *
