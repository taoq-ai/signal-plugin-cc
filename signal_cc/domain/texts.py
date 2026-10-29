"""What the relay says, apart from the prompts themselves (see forms)."""

CHECK = "\N{CHECK MARK}"


def tagged(tag, text):
    return f"[{tag}] {text}"


def hint(live):
    """The hint for an ambiguous plain reply, and the tag a plain reply to it counts for ("" for none)."""
    lines = "\n".join(f"[{w.tag}] {w.summary}" for w in live)
    text = f"Which prompt? {len(live)} waiting:\n{lines}\nQuote one, or start your reply with its tag."
    return text, live[0].tag if len(live) == 1 else ""


def status(live, now):
    """The answer to `status`, and the tag a plain reply to it counts for ("" for none)."""
    if not live:
        return "Nothing is waiting for you.", ""
    lines = [f"[{w.tag}] {w.summary} \N{MIDDLE DOT} {round((now - w.created) / 60)} min ago" for w in live]
    text = f"Waiting for you ({len(live)}):\n" + "\n".join(lines)
    if len(live) > 1:
        text += "\nQuote one, or start your reply with its tag."
    return text, live[0].tag if len(live) == 1 else ""


BACK_AT_MAC = "You're back at the Mac; answer there."
UNREADABLE = "Couldn't read that; try again."
TIMED_OUT = "Timed out; answer on the Mac."
