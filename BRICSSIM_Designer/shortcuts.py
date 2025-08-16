"""
Shim de compatibilidade: módulo movido para design.ui.shortcuts.
Este arquivo será depreciado em versões futuras.
"""
from warnings import warn as _warn
_warn("Módulo movido para design.ui.shortcuts", DeprecationWarning, stacklevel=2)
from design.ui.shortcuts import *  # noqa: F401,F403
