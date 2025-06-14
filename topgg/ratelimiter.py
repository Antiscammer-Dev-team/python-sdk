from collections.abc import Iterable
from types import TracebackType
from collections import deque
from time import time
import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Optional

# Shared reusable __aexit__ logic
async def shared_aexit(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None) -> None:
    async with self.__lock:
        self.__calls.append(time())
        while self._timespan >= self.__period:
            self.__calls.popleft()


class Ratelimiter:
    """Handles ratelimits for a specific endpoint."""

    __slots__ = ('__lock', '__max_calls', '__period', '__calls')

    def __init__(self, max_calls: int, period: float = 1.0):
        self.__calls = deque()
        self.__period = period
        self.__max_calls = max_calls
        self.__lock = asyncio.Lock()

    async def __aenter__(self) -> 'Ratelimiter':
        async with self.__lock:
            if len(self.__calls) >= self.__max_calls:
                until = time() + self.__period - self._timespan
                sleep_time = until - time()
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
        return self

    # Assign shared logic
    __aexit__ = shared_aexit

    @property
    def _timespan(self) -> float:
        return self.__calls[-1] - self.__calls[0] if len(self.__calls) >= 2 else 0.0


class Ratelimiters:
    """Handles ratelimits for multiple endpoints."""

    __slots__ = ('__ratelimiters',)

    def __init__(self, ratelimiters: Iterable[Ratelimiter]):
        self.__ratelimiters = tuple(ratelimiters)

    async def __aenter__(self) -> 'Ratelimiters':
        for ratelimiter in self.__ratelimiters:
            await ratelimiter.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await asyncio.gather(
            *(r.__aexit__(exc_type, exc_val, exc_tb) for r in self.__ratelimiters)
        )
