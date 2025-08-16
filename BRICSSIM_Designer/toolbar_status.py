"""
Shim de compatibilidade: módulo movido para design.ui.toolbar_status.
Este arquivo será depreciado em versões futuras.
"""
from warnings import warn as _warn
_warn("Módulo movido para design.ui.toolbar_status", DeprecationWarning, stacklevel=2)
from design.ui.toolbar_status import *  # noqa: F401,F403
