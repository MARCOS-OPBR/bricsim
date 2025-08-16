# Arquivo dividido automaticamente. Mantido como shim de compat.
try:
    from simulator.core.faceplate_core_extracted import *  # noqa: F401,F403
except Exception:
    pass
try:
    from simulator.ui.faceplate_ui_extracted import *  # noqa: F401,F403
except Exception:
    pass
__all__ = []

