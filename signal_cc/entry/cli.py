"""relay.py <handler>: run a hook handler (or the desk) on the hook JSON from stdin and print its output."""
import json
import sys
import traceback

from ..config import Config
from . import hooks, wiring

HANDLERS = {"start": hooks.start, "permission": hooks.permission, "question": hooks.question,
            "listen": hooks.listen, "quiet": hooks.quiet, "desk": hooks.run_desk}


def failed(cfg, argv, error):
    """Record a handler's failure by its type only: the message may quote the prompt."""
    handler = argv[1] if len(argv) > 1 and argv[1] in HANDLERS else "unknown"
    wiring.journal(cfg).record({"handler": handler, "outcome": "error", "error": type(error).__name__})


def main(argv=sys.argv):
    cfg = Config.load()
    if not cfg:
        return  # not set up: stay out of the way
    try:
        wiring.home(cfg)
    except OSError as e:  # nothing may be written there, the log included
        print(f"signal-plugin-cc: {e}", file=sys.stderr)
        return
    try:
        data = sys.stdin.read()  # the desk runs with no hook input
        out = HANDLERS[argv[1]](cfg, json.loads(data) if data.strip() else {})
    except hooks.Refused as e:
        print(f"signal-plugin-cc: {e}", file=sys.stderr)
        failed(cfg, argv, e)
        return
    except OSError as e:
        print(f"signal-plugin-cc: signal-cli daemon on port {cfg.port}: {e}", file=sys.stderr)
        failed(cfg, argv, e)
        return
    except Exception as e:
        traceback.print_exc()  # a relay failure must never block the session
        failed(cfg, argv, e)
        return
    if out:
        print(json.dumps(out))
