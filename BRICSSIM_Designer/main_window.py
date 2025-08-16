"""
Shim de compatibilidade: módulo movido para scripts.main_window.
Este arquivo será depreciado em versões futuras.
"""
from warnings import warn as _warn
_warn("Módulo movido para scripts.main_window", DeprecationWarning, stacklevel=2)
from scripts.main_window import *  # noqa: F401,F403
