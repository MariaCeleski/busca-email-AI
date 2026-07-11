"""Circuit Breaker pattern for external service calls.

Implements a circuit breaker to protect the system from cascading failures
when external services (Gemini API, Gmail/Microsoft Graph API) are unavailable.

States:
- CLOSED: Normal operation, requests pass through. Failures are tracked.
- OPEN: Circuit tripped after N consecutive failures. Requests fail fast
  without attempting the external call for a cooldown period.
- HALF_OPEN: After cooldown, one test request is allowed through.
  If it succeeds, circuit closes. If it fails, circuit opens again.

Requirements: 6.1, 6.6 (graceful degradation)
"""

from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Callable, Dict, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(str, Enum):
    """Circuit breaker state machine states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerError(Exception):
    """Raised when the circuit is open and calls are being rejected."""

    def __init__(self, service_name: str, remaining_cooldown: float) -> None:
        self.service_name = service_name
        self.remaining_cooldown = remaining_cooldown
        super().__init__(
            f"Circuit breaker OPEN for '{service_name}'. "
            f"Remaining cooldown: {remaining_cooldown:.1f}s"
        )


class CircuitBreaker:
    """Circuit breaker for protecting external service calls.

    Tracks consecutive failures and opens the circuit after a threshold
    is reached. During the open state, calls fail immediately without
    attempting the external service. After a cooldown period, a single
    test call is allowed (half-open state).

    Args:
        service_name: Human-readable name of the protected service.
        failure_threshold: Number of consecutive failures before opening circuit.
        cooldown_seconds: Duration in seconds the circuit stays open before
            transitioning to half-open.
        success_threshold: Number of consecutive successes in half-open state
            required to close the circuit.
    """

    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 5,
        cooldown_seconds: float = 60.0,
        success_threshold: int = 1,
    ) -> None:
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.success_threshold = success_threshold

        self._state: CircuitState = CircuitState.CLOSED
        self._consecutive_failures: int = 0
        self._consecutive_successes: int = 0
        self._last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Current state of the circuit breaker."""
        if self._state == CircuitState.OPEN:
            # Check if cooldown has elapsed → transition to half-open
            if self._last_failure_time is not None:
                elapsed = time.monotonic() - self._last_failure_time
                if elapsed >= self.cooldown_seconds:
                    self._state = CircuitState.HALF_OPEN
                    self._consecutive_successes = 0
                    logger.info(
                        "Circuit breaker '%s' transitioning to HALF_OPEN after %.1fs cooldown",
                        self.service_name,
                        elapsed,
                    )
        return self._state

    @property
    def consecutive_failures(self) -> int:
        """Number of consecutive failures recorded."""
        return self._consecutive_failures

    @property
    def remaining_cooldown(self) -> float:
        """Seconds remaining in the cooldown period (0 if not in OPEN state)."""
        if self._state != CircuitState.OPEN or self._last_failure_time is None:
            return 0.0
        elapsed = time.monotonic() - self._last_failure_time
        remaining = self.cooldown_seconds - elapsed
        return max(0.0, remaining)

    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute a function call protected by the circuit breaker.

        If the circuit is OPEN, raises CircuitBreakerError immediately.
        If the circuit is CLOSED or HALF_OPEN, the function is called.
        On success, failure counters are reset. On failure, counters are incremented.

        Args:
            func: The async callable to execute.
            *args: Positional arguments for the callable.
            **kwargs: Keyword arguments for the callable.

        Returns:
            The result of the callable.

        Raises:
            CircuitBreakerError: If the circuit is open.
            Exception: Any exception raised by the underlying function.
        """
        async with self._lock:
            current_state = self.state

            if current_state == CircuitState.OPEN:
                raise CircuitBreakerError(
                    self.service_name, self.remaining_cooldown
                )

        # Execute the call (outside lock to allow concurrent calls in CLOSED state)
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            # Success
            async with self._lock:
                self._on_success()
            return result

        except Exception as exc:
            # Failure
            async with self._lock:
                self._on_failure()
            raise

    def _on_success(self) -> None:
        """Handle a successful call."""
        if self._state == CircuitState.HALF_OPEN:
            self._consecutive_successes += 1
            if self._consecutive_successes >= self.success_threshold:
                self._state = CircuitState.CLOSED
                self._consecutive_failures = 0
                self._consecutive_successes = 0
                logger.info(
                    "Circuit breaker '%s' CLOSED after successful test call",
                    self.service_name,
                )
        else:
            # In CLOSED state, reset failure counter on success
            self._consecutive_failures = 0
            self._consecutive_successes = 0

    def _on_failure(self) -> None:
        """Handle a failed call."""
        self._consecutive_failures += 1
        self._consecutive_successes = 0
        self._last_failure_time = time.monotonic()

        if self._state == CircuitState.HALF_OPEN:
            # Test call failed → back to OPEN
            self._state = CircuitState.OPEN
            logger.warning(
                "Circuit breaker '%s' re-opened after failed test call "
                "(half-open → open)",
                self.service_name,
            )
        elif self._consecutive_failures >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                "Circuit breaker '%s' OPENED after %d consecutive failures. "
                "Cooldown: %.1fs",
                self.service_name,
                self._consecutive_failures,
                self.cooldown_seconds,
            )

    def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED state."""
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._last_failure_time = None
        logger.info("Circuit breaker '%s' manually reset to CLOSED", self.service_name)

    def get_stats(self) -> Dict[str, Any]:
        """Get current circuit breaker statistics.

        Returns:
            Dict with state, failure count, and cooldown info.
        """
        return {
            "service_name": self.service_name,
            "state": self.state.value,
            "consecutive_failures": self._consecutive_failures,
            "failure_threshold": self.failure_threshold,
            "cooldown_seconds": self.cooldown_seconds,
            "remaining_cooldown": self.remaining_cooldown,
        }


# --- Global circuit breakers for external services ---

# Gemini API circuit breaker
gemini_circuit_breaker = CircuitBreaker(
    service_name="gemini_api",
    failure_threshold=5,
    cooldown_seconds=60.0,
)

# Email Provider API circuit breaker (shared across Gmail/Microsoft)
email_provider_circuit_breaker = CircuitBreaker(
    service_name="email_provider_api",
    failure_threshold=5,
    cooldown_seconds=60.0,
)
