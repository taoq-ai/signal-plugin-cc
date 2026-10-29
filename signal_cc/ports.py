"""What the application needs from the outside world. Adapters implement these; app code depends only
on them, so the use cases run against in-memory fakes in tests."""
import queue
from typing import Callable, List, Protocol, Tuple


class Messenger(Protocol):
    """A chat with the owner."""

    def send(self, text: str) -> int:
        """Send text; return the timestamp a reply quotes."""

    def send_poll(self, question: str, options: List[str], multi: bool) -> int:
        """Send a poll; return the timestamp its votes point at. Raises RuntimeError if refused."""

    def end_poll(self, ts: int) -> None:
        """Close a poll."""

    def subscribe(self) -> Tuple[queue.Queue, Callable[[], None]]:
        """Start receiving: a queue of Reply from the owner (None once the stream ends), and close."""


class Registry(Protocol):
    """The prompts waiting for the owner, shared by every session on the Mac."""

    def claim(self, summary: str, ttl: float) -> str:
        """Register a prompt for ttl seconds under a tag no waiting prompt holds; return the tag."""

    def release(self, tag: str) -> None:
        """The prompt is done."""

    def waiting(self) -> list:
        """The prompts still waiting, as Waiting, oldest first."""

    def latest(self) -> str:
        """The tag the relay's latest message belongs to ("" for none)."""

    def mark_latest(self, tag: str) -> None:
        """Record the tag of the message about to be sent."""


class Gathering(Protocol):
    """The finished sessions waiting for the owner to leave, shared by every session on the Mac, so that the
    sessions that finish together send one digest. An entry is a dict: created, project, first (its digest
    line), sent (when its own message or a digest went out, or None) and digest (the digest it is in, or None)."""

    def enter(self, tag: str, project: str, first: str) -> None:
        """Add the finished session's prompt, tagged tag."""

    def entries(self) -> dict:
        """Every entry, by tag."""

    def update(self, tag: str, **fields) -> None:
        """Change fields of an entry, if it is still there."""

    def leave(self, tag: str) -> None:
        """The prompt is done."""

    def lead(self) -> bool:
        """Take the lead of the next digest, unless another listener holds it."""

    def unlead(self) -> None:
        """Let the lead go."""


class Journal(Protocol):
    """A local record of how each relayed prompt ended. Entries never hold message text or numbers."""

    def record(self, entry: dict) -> None:
        """Add one entry, stamped with the time. Never raises: the log must not break the relay."""


class Presence(Protocol):
    """Whether the owner is at the Mac."""

    def away(self) -> bool:
        """Away long enough that prompts should go to Signal."""

    def returned(self) -> bool:
        """Just came back (input in the last few seconds)."""

    def set_switch(self, on: bool) -> None:
        """Turn the away switch on or off; while on, the owner is away whatever the Mac's idle time."""

    def switch_on(self) -> bool:
        """Whether the away switch is on."""
