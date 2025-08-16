"""
Shim de compatibilidade: módulo movido para design.ui.splash.
Este arquivo será depreciado em versões futuras.
"""
from warnings import warn as _warn
_warn("Módulo movido para design.ui.splash", DeprecationWarning, stacklevel=2)
from design.ui.splash import *  # noqa: F401,F403
