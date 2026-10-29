"""State shared by every session on the Mac, kept in files under the config home."""
import fcntl
import json
import os
import secrets
import sys
import time

from ..domain.model import Waiting
from . import private


class FileRegistry:
    """Registry: one file per waiting prompt under pending/, and the latest tag in last."""

    def __init__(self, home):
        self.home = home
        self.pending = home / "pending"

    def claim(self, summary, ttl):
        """The claim exists before the prompt is sent, so no other session takes a plain reply to it."""
        private.home(self.home)
        private.folder(self.pending)
        now = time.time()
        for p in self.pending.iterdir():  # drop the claims of prompts that ended without cleaning up
            try:
                if json.loads(p.read_text())["deadline"] < now:
                    p.unlink(missing_ok=True)
            except (OSError, ValueError, KeyError):
                pass
        while True:
            tag = secrets.token_hex(2)
            try:
                with private.open_file(self.pending / tag, "x") as f:
                    json.dump({"created": now, "deadline": now + ttl, "summary": summary}, f)
                return tag
            except FileExistsError:
                continue

    def release(self, tag):
        (self.pending / tag).unlink(missing_ok=True)

    def waiting(self):
        if not self.pending.exists():
            return []
        now = time.time()
        live = []
        for p in self.pending.iterdir():
            try:
                d = json.loads(p.read_text())
            except (OSError, ValueError):
                continue
            if d["deadline"] > now:
                live.append(Waiting(d["created"], p.name, d["summary"]))
        return sorted(live)

    def latest(self):
        try:
            return (self.home / "last").read_text()
        except OSError:
            return ""

    def mark_latest(self, tag):
        private.home(self.home)
        with private.open_file(self.home / "last", "w") as f:
            f.write(tag)


class AwaySwitch:
    """The away switch: on while the file away exists."""

    def __init__(self, home):
        self.home = home
        self.path = home / "away"

    def on(self):
        return self.path.exists()

    def set(self, on):
        if on:
            private.home(self.home)
            private.open_file(self.path, "a").close()
        else:
            self.path.unlink(missing_ok=True)


class FileJournal:
    """Journal: one JSON line per entry in relay.log, appended by every session on the Mac."""

    def __init__(self, home):
        self.path = home / "relay.log"

    def record(self, entry):
        line = json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **entry}) + "\n"
        try:
            private.home(self.path.parent)
            with private.open_file(self.path, "a") as f:
                f.write(line)  # one short write per line, so sessions appending at once don't interleave
        except OSError as e:
            print(f"signal-plugin-cc: {self.path}: {e}", file=sys.stderr)


class Listeners:
    """The pid of each session's listener, under listeners/."""

    def __init__(self, home):
        self.dir = home / "listeners"

    def _path(self, session):
        return self.dir / f"{session}.pid"

    def get(self, session):
        try:
            return int(self._path(session).read_text())
        except (OSError, ValueError):
            return None

    def set(self, session, pid):
        private.home(self.dir.parent)
        private.folder(self.dir)
        with private.open_file(self._path(session), "w") as f:
            f.write(str(pid))

    def clear(self, session, pid=None):
        """Forget the session's listener; with pid, only if it is still that one."""
        if pid is None or self.get(session) == pid:
            private.remove(self._path(session))


class FileGathering:
    """Gathering: one JSON file per entry under gather/, and the lead as a lock on gather.lock, which a listener
    that dies lets go of."""

    def __init__(self, home):
        self.dir = home / "gather"
        self.lock = DeskLock(home, "gather.lock")

    def _write(self, tag, row):
        tmp = self.dir / f".{tag}.{secrets.token_hex(4)}"
        with private.open_file(tmp, "x") as f:
            json.dump(row, f)
        os.replace(tmp, self.dir / tag)  # whole, so a reader never sees half of it; replaces a symlink, never follows

    def enter(self, tag, project, first):
        private.home(self.dir.parent)
        private.folder(self.dir)
        self._write(tag, {"created": time.time(), "project": project, "first": first, "sent": None, "digest": None})

    def entries(self):
        out = {}
        for p in self.dir.glob("[!.]*") if self.dir.exists() else ():
            try:
                out[p.name] = json.loads(p.read_text())
            except (OSError, ValueError):
                continue
        return out

    def update(self, tag, **fields):
        row = self.entries().get(tag)
        if row is not None:
            self._write(tag, {**row, **fields})

    def leave(self, tag):
        (self.dir / tag).unlink(missing_ok=True)

    def lead(self):
        return self.lock.acquire()

    def unlead(self):
        self.lock.release()


class DeskLock:
    """Held by the one desk that runs on the Mac."""

    def __init__(self, home, name="desk.lock"):
        self.path = home / name
        self.file = None

    def acquire(self):
        private.home(self.path.parent)
        self.file = private.open_file(self.path, "w")
        try:
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            self.release()
            return False

    def release(self):
        if self.file:
            self.file.close()
            self.file = None
