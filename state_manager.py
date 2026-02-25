"""
Session state persistence for CoirnaBot.

Saves/restores balance, monitor, and optimizer state across restarts
so that trades, rankings, and capital positions survive deployments.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

STATE_DIR = Path("state")
STATE_FILE = STATE_DIR / "session.json"
STATE_BACKUP = STATE_DIR / "session.json.bak"
STATE_VERSION = 1


class StateManager:
    """Coordinates saving and loading session state across restarts."""

    def __init__(self, save_interval: float = 60.0):
        self._save_interval = save_interval
        self._skip_save = False
        self._running = True
        STATE_DIR.mkdir(exist_ok=True)

    def stop(self) -> None:
        self._running = False

    def save(self, balance, monitor, optimizer, demo_fetcher=None) -> bool:
        """Save all component state to disk atomically."""
        if self._skip_save:
            return False
        try:
            state = {
                "version": STATE_VERSION,
                "saved_at": time.time(),
                "balance": balance.to_state_dict(),
                "monitor": monitor.to_state_dict(),
                "optimizer": optimizer.to_state_dict(),
            }
            if demo_fetcher is not None:
                state["demo_fetcher"] = demo_fetcher.to_state_dict()
            # Backup existing file
            if STATE_FILE.exists():
                STATE_BACKUP.write_bytes(STATE_FILE.read_bytes())

            # Atomic write: write to temp, then rename
            tmp_path = STATE_FILE.with_suffix(".tmp")
            with open(tmp_path, "w") as f:
                json.dump(state, f)
            os.replace(str(tmp_path), str(STATE_FILE))

            trade_count = len(state["monitor"].get("trades", []))
            logger.info(f"[State] Saved session state ({trade_count} trades)")
            return True
        except Exception as e:
            logger.error(f"[State] Failed to save: {e}")
            return False

    def load(self) -> dict | None:
        """Load state from disk. Returns None if no valid state file."""
        if not STATE_FILE.exists():
            return None
        try:
            with open(STATE_FILE) as f:
                state = json.load(f)
            version = state.get("version", 0)
            if version != STATE_VERSION:
                logger.warning(
                    f"[State] Version mismatch: file={version}, expected={STATE_VERSION}"
                )
                return None
            saved_at = state.get("saved_at", 0)
            age_min = (time.time() - saved_at) / 60
            logger.info(f"[State] Found saved state ({age_min:.1f} min old)")
            return state
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[State] Failed to load: {e}")
            # Try backup
            if STATE_BACKUP.exists():
                try:
                    with open(STATE_BACKUP) as f:
                        state = json.load(f)
                    logger.info("[State] Loaded from backup")
                    return state
                except Exception:
                    pass
            return None

    def clear(self) -> None:
        """Delete saved state so next startup begins fresh."""
        self._skip_save = True
        for f in [STATE_FILE, STATE_BACKUP]:
            if f.exists():
                f.unlink()
        logger.info("[State] Cleared saved state (fresh restart)")

    async def periodic_save(self, balance, monitor, optimizer, demo_fetcher=None) -> None:
        """Async task that saves state periodically."""
        while self._running:
            await asyncio.sleep(self._save_interval)
            if self._running:
                self.save(balance, monitor, optimizer, demo_fetcher)
