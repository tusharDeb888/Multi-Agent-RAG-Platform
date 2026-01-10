"""
Resilience utilities for production hardening.
Includes Retry logic with exponential backoff and Circuit Breaker pattern.
"""
import time
import functools
import random
from typing import Type, Union, Tuple, Callable, Any, Optional
from loguru import logger

def retry(
    exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception,
    tries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    jitter: float = 0.1,
    logger_fn: Optional[Callable] = logger.warning
):
    """
    Retry decorator with exponential backoff and jitter.
    
    :param exceptions: Exception or tuple of exceptions to catch.
    :param tries: Total number of attempts (default 3).
    :param delay: Initial delay in seconds (default 1.0).
    :param backoff: Multiplier for delay after each failure (default 2.0).
    :param jitter: Random jitter factor to add to delay (default 0.1).
    :param logger_fn: Function to log retries (default loguru.logger.warning).
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            mtries, mdelay = tries, delay
            while mtries > 1:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    sleep_time = mdelay + (random.uniform(-jitter, jitter) * mdelay)
                    if logger_fn:
                        logger_fn(f"Retrying {func.__name__} due to {e.__class__.__name__}: {e}. Next attempt in {sleep_time:.2f}s...")
                    time.sleep(sleep_time)
                    mtries -= 1
                    mdelay *= backoff
            return func(*args, **kwargs)
        return wrapper
    return decorator

class CircuitBreakerOpenException(Exception):
    pass

class CircuitBreaker:
    """
    Circuit Breaker pattern to prevent cascading failures.
    """
    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time = 0
        self.state = "CLOSED" # CLOSED, OPEN, HALF-OPEN

    def _check_state(self):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF-OPEN"
                logger.info(f"Circuit Breaker '{self.name}' transitioning to HALF-OPEN.")
            else:
                raise CircuitBreakerOpenException(f"Circuit Breaker '{self.name}' is OPEN. Fast-failing.")

    def call(self, func: Callable, *args, **kwargs) -> Any:
        self._check_state()
        
        try:
            result = func(*args, **kwargs)
            if self.state == "HALF-OPEN":
                logger.info(f"Circuit Breaker '{self.name}' recovered (CLOSED).")
                self.reset()
            return result
        except Exception as e:
            self._record_failure()
            raise e

    def _record_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.failure_threshold:
            if self.state != "OPEN":
                logger.error(f"Circuit Breaker '{self.name}' OPENED after {self.failures} failures.")
            self.state = "OPEN"

    def reset(self):
        self.failures = 0
        self.state = "CLOSED"
