"""The composition root: the one place that picks adapters for the ports."""
from ..adapters.files import FileRegistry
from ..adapters.macos import MacPresence
from ..adapters.signal_cli import SignalCli
from ..app.conversation import Conversation


def conversation(cfg):
    return Conversation(SignalCli(cfg), FileRegistry(cfg.home), MacPresence(cfg.idle), cfg.wait)
