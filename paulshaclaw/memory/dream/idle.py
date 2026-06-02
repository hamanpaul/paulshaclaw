import os
from typing import Callable, Sequence


def is_idle(max_load: float = 1.0, probe: Callable[[], Sequence[float]] = os.getloadavg) -> bool:
    """Return True when system is considered idle using the 1-minute load average.

    probe must be a callable that returns a sequence (like os.getloadavg()).
    Scalars are not supported and will raise TypeError. If the load cannot be
    determined due to OSError, AttributeError, or IndexError, the function
    fails safe and returns True.
    """
    try:
        result = probe()
        # Only accept sequence-style results (tuple/list); disallow scalars.
        if not hasattr(result, "__iter__") or not hasattr(result, "__getitem__"):
            raise TypeError("probe must return a sequence like os.getloadavg()")
        load = float(result[0])
        return load <= float(max_load)
    except (OSError, AttributeError, IndexError):
        # fail-safe: if we can't determine load, allow running
        return True
