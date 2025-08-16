"""
Shim de compatibilidade: módulo movido para design.ui.controle.
Este arquivo será depreciado em versões futuras.
"""
from warnings import warn as _warn
_warn("Módulo movido para design.ui.controle", DeprecationWarning, stacklevel=2)
from design.ui.controle import *  # noqa: F401,F403
