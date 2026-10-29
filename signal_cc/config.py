"""The user's settings, read from <home>/config.json."""
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HOME = Path.home() / ".config" / "signal-plugin-cc"


@dataclass(frozen=True)
class Config:
    owner: str  # your Signal number; only its replies are read
    home: Path  # config, pending prompts and the daemon log
    bot: str = ""  # a separate bot number; empty means your own account, through Note to Self
    port: int = 8299  # signal-cli HTTP daemon port
    wait: int = 300  # seconds to wait for a reply
    idle: int = 60  # seconds without input before the Mac counts as unattended
    listen: int = 3600  # seconds a finished session waits for a reply that continues it
    signal_cli: str = "signal-cli"

    @property
    def account(self):
        """The account signal-cli runs as."""
        return self.bot or self.owner

    @property
    def note_to_self(self):
        return self.account == self.owner

    @property
    def pending(self):
        return self.home / "pending"

    @classmethod
    def load(cls):
        """The config, or None when it is missing or invalid (the plugin then stays out of the way)."""
        home = Path(os.environ.get("SIGNAL_CC_HOME") or DEFAULT_HOME)
        path = home / "config.json"
        try:
            raw = json.loads(path.read_text())
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as e:
            print(f"signal-plugin-cc: {path}: {e}", file=sys.stderr)
            return None
        try:
            cfg = cls(home=home, **raw)
        except TypeError as e:  # a missing or unknown key
            print(f"signal-plugin-cc: {path}: {e}", file=sys.stderr)
            return None
        if not cfg.owner:
            print(f"signal-plugin-cc: {path}: owner is required", file=sys.stderr)
            return None
        return cfg
