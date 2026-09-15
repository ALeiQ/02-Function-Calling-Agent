"""Conversation session and message-history management.

Keeps the per-session role/message list (and optional cheap persistence) that
the agent loop grows with tool results.

TODO(milestone 2): implement session create/get/append and persistence.
"""