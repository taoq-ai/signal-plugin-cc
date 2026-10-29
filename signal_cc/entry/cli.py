"""relay.py <handler>: run a hook handler (or the desk) on the hook JSON from stdin and print its output."""
import json
import sys
import traceback

from ..config import Config
from . import hooks

HANDLERS = {"start": hooks.start, "permission": hooks.permission, "question": hooks.question,
            "listen": hooks.listen, "quiet": hooks.quiet, "desk": hooks.run_desk}


def main(argv=sys.argv):
    cfg = Config.load()
    if not cfg:
        return  # not set up: stay out of the way
    try:
        data = sys.stdin.read()  # the desk runs with no hook input
        out = HANDLERS[argv[1]](cfg, json.loads(data) if data.strip() else {})
    except OSError as e:
        print(f"signal-plugin-cc: signal-cli daemon on port {cfg.port}: {e}", file=sys.stderr)
        return
    except Exception:
        traceback.print_exc()  # a relay failure must never block the session
        return
    if out:
        print(json.dumps(out))
