"""
Shim de compatibilidade: módulo movido para scripts.trends.
Este arquivo será depreciado em versões futuras.
"""
from warnings import warn as _warn
_warn("Módulo movido para scripts.trends", DeprecationWarning, stacklevel=2)
from scripts.trends import *  # noqa: F401,F403
