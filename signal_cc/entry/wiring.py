"""The composition root: the one place that picks and builds adapters for the ports."""
from ..adapters.files import AwaySwitch, DeskLock, FileJournal, FileRegistry, Listeners
from ..adapters import private
from ..adapters.macos import MacPresence
from ..adapters.signal_cli import SignalCli
from ..app.conversation import Conversation


def home(cfg):
    """Check the config home before any hook runs: the user's own, and private."""
    private.home(cfg.home)


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


def journal(cfg):
    return FileJournal(cfg.home)


def conversation(cfg, session):
    return Conversation(daemon(cfg), registry(cfg), presence(cfg), cfg.wait, journal(cfg), session)
