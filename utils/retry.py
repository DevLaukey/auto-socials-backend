"""
Generic retry utility.

Used for:
- Non-Celery retryable operations
- Simple fault tolerance where Celery is not involved
"""

import time
from typing import Callable, Type, Tuple


def retry(
    func: Callable,
    retries: int = 3,
    delay: float = 1.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """
    Retry a function call.

    Example:
        result = retry(lambda: risky_call(), retries=5, delay=2)
    """

    last_exception = None

    for attempt in range(1, retries + 1):
        try:
            return func()
        except exceptions as exc:
            last_exception = exc
            if attempt < retries:
                time.sleep(delay)

    raise last_exception
