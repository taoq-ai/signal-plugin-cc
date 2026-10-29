"""Relay Claude Code prompts to Signal and read the answer back.

Layers, inner to outer (each imports only from the ones before it):
  domain    the rules, no I/O: routing, forms, texts
  ports     the interfaces the use cases need: Messenger, Registry, Presence
  app       the use cases: ask, continue a session, answer commands
  adapters  signal-cli, files, macOS idle time, processes
  entry     the Claude Code hooks and the desk, and the wiring between them
"""
