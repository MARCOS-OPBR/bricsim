"""
Shim de compatibilidade: módulo movido para design.ui.singleton.
Este arquivo será depreciado em versões futuras.
"""
from warnings import warn as _warn
_warn("Módulo movido para design.ui.singleton", DeprecationWarning, stacklevel=2)
from design.ui.singleton import *  # noqa: F401,F403
