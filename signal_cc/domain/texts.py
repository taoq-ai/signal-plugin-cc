"""What the relay says, apart from the prompts themselves (see forms)."""
from .model import AT_MAC, CLOSED

CHECK = "\N{CHECK MARK}"


def tagged(tag, text):
    return f"[{tag}] {text}"


def hint(live):
    """The hint for an ambiguous plain reply, and the tag a plain reply to it counts for ("" for none)."""
    lines = "\n".join(f"[{w.tag}] {w.summary}" for w in live)
    text = f"Which prompt? {len(live)} waiting:\n{lines}\nQuote one, or start your reply with its tag."
    return text, live[0].tag if len(live) == 1 else ""


def status(live, now, away):
    """The answer to `status`, and the tag a plain reply to it counts for ("" for none). away: the switch."""
    switch = AWAY_ON if away else AWAY_OFF
    if not live:
        return f"Nothing is waiting for you.\n{switch}", ""
    lines = [f"[{w.tag}] {w.summary} \N{MIDDLE DOT} {round((now - w.created) / 60)} min ago" for w in live]
    text = f"Waiting for you ({len(live)}):\n" + "\n".join(lines)
    if len(live) > 1:
        text += "\nQuote one, or start your reply with its tag."
    return f"{text}\n{switch}", live[0].tag if len(live) == 1 else ""


AWAY_ON = "Away switch on: prompts come here until you send back or type a prompt at the Mac."
AWAY_OFF = "Away switch off: prompts come here once the Mac is idle."
BACK_AT_MAC = "You're back at the Mac; answer there."
UNREADABLE = "Couldn't read that; try again."
TIMED_OUT = "Timed out; answer on the Mac."
STOPPED = {  # the notice on a waiting prompt whose listener hooks.quiet stopped
    AT_MAC: "Answered at the Mac; replies here no longer reach this session.",
    CLOSED: "The session closed; replies here no longer reach it.",
}
