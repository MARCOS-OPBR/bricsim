"""
Shim de compatibilidade: módulo movido para design.ui.functions.
Este arquivo será depreciado em versões futuras.
"""
from warnings import warn as _warn
_warn("Módulo movido para design.ui.functions", DeprecationWarning, stacklevel=2)
from design.ui.functions import *  # noqa: F401,F403
