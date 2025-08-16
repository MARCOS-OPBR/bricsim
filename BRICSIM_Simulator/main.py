"""
Shim de compatibilidade: módulo movido para design.ui.main.
Este arquivo será depreciado em versões futuras.
"""
from warnings import warn as _warn
_warn("Módulo movido para design.ui.main", DeprecationWarning, stacklevel=2)
from design.ui.main import *  # noqa: F401,F403
