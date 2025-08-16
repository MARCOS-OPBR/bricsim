"""
Shim de compatibilidade: módulo movido para design.ui.resources.
Este arquivo será depreciado em versões futuras.
"""
from warnings import warn as _warn
_warn("Módulo movido para design.ui.resources", DeprecationWarning, stacklevel=2)
from design.ui.resources import *  # noqa: F401,F403
