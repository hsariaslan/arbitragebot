"""
Multi-config logging context (v0.31.0-beta).

A single `ConfigContextVar` is set by the Orchestrator before each per-config
sweep tick and cleared after. A `ConfigPrefixFilter` (installed on the root
logger by `setup_logging()`) reads the ContextVar and:

  1. Prepends `[GROUP_x][CONFIG_y]` to every record's message so the prefix
     ends up in both the file log and the console.
  2. Stamps `record.config_group_id` and `record.config_id` on the LogRecord
     so the DashboardLogHandler can surface them in the broadcast payload
     and the cascading group → config dropdown can filter without re-parsing
     the message string.

Records emitted by SHARED subsystems (fetchers, FundingMonitor, Auth,
Capacity, Settings, Migration) run with the ContextVar unset — they get
no prefix and are routed to the dashboard "Universal" bucket.

`asyncio.create_task` snapshots the current context at task-creation time,
so any per-config component that spawns a long-lived task implicitly
inherits the prefix. `spawn_config_task()` is a small helper for cases
where we want to be explicit.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
from typing import Any, Coroutine

# (group_id, group_name, config_id, config_name) — name fields included so
# the prefix is human-readable without a registry lookup at log-emission time.
ConfigContextVar: contextvars.ContextVar[tuple[str, str, str, str] | None] = (
    contextvars.ContextVar("arbitragebot_config_ctx", default=None)
)


def set_config_context(
    group_id: str, group_name: str, config_id: str, config_name: str
) -> contextvars.Token:
    """Set the active config context. Returns a token to be passed to reset()."""
    return ConfigContextVar.set((group_id, group_name, config_id, config_name))


def reset_config_context(token: contextvars.Token) -> None:
    ConfigContextVar.reset(token)


def get_config_context() -> tuple[str, str, str, str] | None:
    return ConfigContextVar.get()


class ConfigPrefixFilter(logging.Filter):
    """Stamps active config context onto each LogRecord.

    Idempotent across multiple handlers: the same record object passes
    through every handler's filter list, so we tag a `_config_prefixed`
    sentinel on the record after the first pass to avoid double-prefixing.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "_config_prefixed", False):
            return True

        ctx = ConfigContextVar.get()
        if ctx is not None:
            group_id, group_name, config_id, config_name = ctx
            record.config_group_id = group_id
            record.config_group_name = group_name
            record.config_id = config_id
            record.config_name = config_name
            # Prepend prefix to the formatted message. Use record.msg so we
            # don't double-format (record.message is built later by the
            # formatter).
            try:
                record.msg = f"[{group_name}][{config_name}] {record.msg}"
            except Exception:
                pass
        else:
            record.config_group_id = None
            record.config_group_name = None
            record.config_id = None
            record.config_name = None
        record._config_prefixed = True
        return True


def spawn_config_task(coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
    """Spawn an asyncio task that inherits the current config context.

    asyncio.create_task already copies the current context, so this is mostly
    a documentation helper — but having a single entry point makes it easy to
    audit per-config task spawns later.
    """
    return asyncio.create_task(coro)
