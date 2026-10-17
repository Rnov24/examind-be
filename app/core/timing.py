import time
import logging
from contextlib import contextmanager

logger = logging.getLogger("examind.perf")


@contextmanager
def log_query_timing(endpoint_name: str):
    """Lightweight context manager for query timing logs at debug level."""
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000.0
        logger.debug(f"[QueryTiming] {endpoint_name} completed in {duration_ms:.2f}ms")
