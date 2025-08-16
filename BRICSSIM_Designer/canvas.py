# Arquivo dividido automaticamente. Mantido como shim de compat.
try:
    from simulator.core.canvas_core_extracted import *  # noqa: F401,F403
except Exception:
    pass
try:
    from simulator.ui.canvas_ui_extracted import *  # noqa: F401,F403
except Exception:
    pass
__all__ = []

