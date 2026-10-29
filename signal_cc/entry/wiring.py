"""The composition root: the one place that picks and builds adapters for the ports."""
from ..adapters.files import AwaySwitch, DeskLock, FileRegistry, Listeners
from ..adapters.macos import MacPresence
from ..adapters.signal_cli import SignalCli
from ..app.conversation import Conversation


def daemon(cfg):
    return SignalCli(cfg)


def registry(cfg):
    return FileRegistry(cfg.home)


def listeners(cfg):
    return Listeners(cfg.home)


def desk_lock(cfg):
    return DeskLock(cfg.home)


def presence(cfg):
    return MacPresence(cfg.idle, AwaySwitch(cfg.home))


def conversation(cfg):
    return Conversation(daemon(cfg), registry(cfg), presence(cfg), cfg.wait)
