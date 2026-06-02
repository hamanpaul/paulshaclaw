import os
from typing import Callable


def is_idle(max_load: float = 1.0, probe: Callable = os.getloadavg) -> bool:
    """Return True when system is considered idle using 1-minute load.

    probe should be a callable that returns a sequence like os.getloadavg()
    or a single numeric value. If load cannot be determined, fail-safe to True.
    """
    try:
        result = probe()
        # support sequence-like results (e.g., (1min, 5min, 15min))
        if hasattr(result, "__iter__"):
            load = float(result[0])
        else:
            load = float(result)
        return load <= float(max_load)
    except (OSError, AttributeError, IndexError):
        # fail-safe: if we can't determine load, allow running
        return True
