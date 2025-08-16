"""
Shim de compatibilidade: reexporta de scripts.
"""

from warnings import warn

warn("Módulo movido para scripts/main.py", DeprecationWarning, stacklevel=2)
from scripts.main import *  # noqa: F401,F403
