"""
TraceEventBus — in-process pub/sub for live trace streaming.

The LangGraph pipeline publishes events here as each agent completes.
The SSE endpoint subscribes per claim_id and forwards events to the browser.
Events are also persisted to SQLite by the pipeline (not the bus itself).
"""
import asyncio
from app.models.trace import TraceEvent

# Sentinel pushed to a subscriber queue to signal the stream is done.
_STREAM_DONE = object()


class TraceEventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, claim_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(claim_id, []).append(q)
        return q

    def unsubscribe(self, claim_id: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(claim_id, [])
        if queue in subs:
            subs.remove(queue)

    async def publish(self, event: TraceEvent) -> None:
        for q in self._subscribers.get(event.claim_id, []):
            await q.put(event)

    async def close_stream(self, claim_id: str) -> None:
        """Push sentinel to all subscribers so they know the pipeline is done."""
        for q in self._subscribers.get(claim_id, []):
            await q.put(_STREAM_DONE)

    @staticmethod
    def is_done(item: object) -> bool:
        return item is _STREAM_DONE


# Process-level singleton — imported by the FastAPI app and the LangGraph pipeline.
event_bus = TraceEventBus()
