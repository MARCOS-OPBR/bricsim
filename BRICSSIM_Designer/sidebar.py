"""
Shim de compatibilidade: módulo movido para design.ui.sidebar.
Este arquivo será depreciado em versões futuras.
"""
from warnings import warn as _warn
_warn("Módulo movido para design.ui.sidebar", DeprecationWarning, stacklevel=2)
from design.ui.sidebar import *  # noqa: F401,F403
