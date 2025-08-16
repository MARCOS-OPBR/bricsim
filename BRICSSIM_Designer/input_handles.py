"""
Shim de compatibilidade: módulo movido para design.ui.input_handles.
Este arquivo será depreciado em versões futuras.
"""
from warnings import warn as _warn
_warn("Módulo movido para design.ui.input_handles", DeprecationWarning, stacklevel=2)
from design.ui.input_handles import *  # noqa: F401,F403
