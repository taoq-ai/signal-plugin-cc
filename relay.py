#!/usr/bin/env python3
"""Hook entry point: relay.py start|permission|question|listen|quiet|desk, with the hook's JSON on stdin."""
import sys

try:
    import fcntl  # noqa: F401  the state files lock with it
except ImportError:  # Windows: the relay cannot run, so stay out of the way
    sys.exit(0)

from signal_cc.entry.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
