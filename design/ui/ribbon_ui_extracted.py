"""
Shim de compatibilidade: módulo movido para design.ui.ribbon.
Este arquivo será depreciado em versões futuras.
"""
from warnings import warn as _warn
_warn("Módulo movido para design.ui.ribbon", DeprecationWarning, stacklevel=2)
from design.ui.ribbon import *
