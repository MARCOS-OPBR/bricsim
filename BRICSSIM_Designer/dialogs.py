"""
Shim de compatibilidade: módulo movido para design.ui.dialogs.
Este arquivo será depreciado em versões futuras.
"""
from warnings import warn as _warn
_warn("Módulo movido para design.ui.dialogs", DeprecationWarning, stacklevel=2)
from design.ui.dialogs import *  # noqa: F401,F403
