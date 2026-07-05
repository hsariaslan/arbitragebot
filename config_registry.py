"""
Multi-config registry for ArbitrageBot v0.31.0-beta.

A registry holds multiple `ConfigGroup`s, each containing multiple `Config`s.
Each Config is an independent strategy variation simulated in parallel.

The registry is the source of truth for which configs exist, their order,
which is the default (selected on dashboard load), which are primaries
(shown as header rows), and which one is the super-primary (the only
config allowed to use non-simulation execution mode + real Binance Futures
positions).

Schema v2 (settings.json):
{
  "schema_version": 2,
  "shared": {
    "execution_mode": "simulation",       # super-primary inherits
    "hedge_execution_mode": "simulation", # super-primary inherits
    "ip_whitelist_enabled": false,
    "ip_whitelist": [],
    "transfer_configs": {...},
    "super_primary_config_id": "<uuid>"
  },
  "groups": [
    {
      "id": "<uuid>",
      "name": "Group 1",
      "initial_capital": 1000.0,
      "order": 0,
      "configs": [
        {
          "id": "<uuid>",
          "name": "Config 1",
          "description": "",
          "is_primary": true,
          "is_default": true,
          "order": 0,
          "settings": { /* all per-config keys */ }
        }
      ]
    }
  ]
}
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterator

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 2

# Keys that live in settings["shared"], NOT in per-config settings blobs.
# Anything not in this list is per-config.
SHARED_KEYS: set[str] = {
    "execution_mode",
    "hedge_execution_mode",
    "ip_whitelist_enabled",
    "ip_whitelist",
    "transfer_configs",
    "super_primary_config_id",
}

# Keys that are removed from per-config blobs because they live elsewhere
# (group-level capital or shared section). When migrating v1 → v2 we strip
# these from the per-config dict.
STRIP_FROM_PER_CONFIG: set[str] = SHARED_KEYS | {
    "total_capital",  # → group.initial_capital
}


def _strip_per_config(settings: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of `settings` with shared/group-level keys removed.

    Single source of truth for the strip operation — used by `add_config`,
    `update_config_settings`, `clone_config`, and the post-load cleanup so
    keys like `total_capital` can never leak into per-config storage from
    any path (paste payload, frontend cache, legacy migration, file edit).
    """
    return {k: v for k, v in settings.items() if k not in STRIP_FROM_PER_CONFIG}


def _new_id() -> str:
    """Stable internal ID for a group or config."""
    return uuid.uuid4().hex[:12]


@dataclass
class Config:
    """A single strategy variation within a group."""

    id: str
    group_id: str
    name: str
    description: str
    is_primary: bool
    is_default: bool
    order: int
    settings: dict[str, Any]
    _dirty: bool = field(default=False, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "is_primary": self.is_primary,
            "is_default": self.is_default,
            "order": self.order,
            "settings": self.settings,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any], group_id: str) -> "Config":
        # Self-heal: strip shared/group-level keys at load time so historical
        # bad writes (e.g., legacy migration leftovers, hand-edited file)
        # don't poison the runtime. Without this, `total_capital=1000` from
        # an old per-config blob would silently override the group's
        # initial_capital downstream and produce phantom 50% drawdowns when
        # peak/current bases drift apart.
        return cls(
            id=str(d.get("id") or _new_id()),
            group_id=group_id,
            name=str(d.get("name", "Config")),
            description=str(d.get("description", "")),
            is_primary=bool(d.get("is_primary", False)),
            is_default=bool(d.get("is_default", False)),
            order=int(d.get("order", 0)),
            settings=_strip_per_config(d.get("settings", {})),
        )

    def mark_dirty(self) -> None:
        self._dirty = True


@dataclass
class ConfigGroup:
    """A capital tier (e.g., $1k, $3k, $5k) holding multiple configs."""

    id: str
    name: str
    initial_capital: float
    order: int
    configs: list[Config]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "initial_capital": self.initial_capital,
            "order": self.order,
            "configs": [c.to_dict() for c in sorted(self.configs, key=lambda x: x.order)],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ConfigGroup":
        gid = str(d.get("id") or _new_id())
        configs = [
            Config.from_dict(c, gid) for c in d.get("configs", [])
        ]
        return cls(
            id=gid,
            name=str(d.get("name", "Group")),
            initial_capital=float(d.get("initial_capital", 1000.0)),
            order=int(d.get("order", 0)),
            configs=configs,
        )


class ConfigRegistry:
    """The full multi-config tree plus shared cross-config settings."""

    def __init__(self, shared: dict[str, Any], groups: list[ConfigGroup]):
        self.shared: dict[str, Any] = dict(shared)
        self.groups: list[ConfigGroup] = list(groups)
        self._index_dirty: bool = True
        self._validate_invariants(repair=True)

    # ----- iteration ---------------------------------------------------
    def iter_configs(self) -> Iterator[Config]:
        for g in sorted(self.groups, key=lambda x: x.order):
            for c in sorted(g.configs, key=lambda x: x.order):
                yield c

    def all_configs(self) -> list[Config]:
        return list(self.iter_configs())

    def find_config(self, config_id: str) -> Config | None:
        for c in self.iter_configs():
            if c.id == config_id:
                return c
        return None

    def find_group(self, group_id: str) -> ConfigGroup | None:
        for g in self.groups:
            if g.id == group_id:
                return g
        return None

    def find_group_for_config(self, config_id: str) -> ConfigGroup | None:
        for g in self.groups:
            if any(c.id == config_id for c in g.configs):
                return g
        return None

    # ----- properties --------------------------------------------------
    @property
    def super_primary_id(self) -> str | None:
        return self.shared.get("super_primary_config_id")

    @property
    def super_primary_config(self) -> Config | None:
        sid = self.super_primary_id
        return self.find_config(sid) if sid else None

    @property
    def default_config(self) -> Config | None:
        for c in self.iter_configs():
            if c.is_default:
                return c
        # Fallback: first config
        for c in self.iter_configs():
            return c
        return None

    @property
    def primary_configs(self) -> list[Config]:
        return [c for c in self.iter_configs() if c.is_primary]

    # ----- group CRUD --------------------------------------------------
    def add_group(self, name: str | None = None, initial_capital: float = 1000.0) -> ConfigGroup:
        order = max((g.order for g in self.groups), default=-1) + 1
        if not name:
            name = f"Group {len(self.groups) + 1}"
        g = ConfigGroup(
            id=_new_id(),
            name=name,
            initial_capital=float(initial_capital),
            order=order,
            configs=[],
        )
        self.groups.append(g)
        self._index_dirty = True
        return g

    def remove_group(self, group_id: str) -> None:
        g = self.find_group(group_id)
        if g is None:
            raise KeyError(f"Group not found: {group_id}")
        # Auto-reassign default/super-primary/primary BEFORE removal.
        # Only block if this is the *last* group with any configs (then
        # there's nothing left to reassign to).
        survivor_configs = [c for og in self.groups if og.id != group_id for c in og.configs]
        if not survivor_configs and g.configs:
            raise ValueError(
                "Cannot remove the last group with configs — at least one config "
                "must remain in the registry."
            )
        # Pick survivor (= first config of first remaining group, in registry order)
        survivor = None
        if survivor_configs:
            for og in sorted(self.groups, key=lambda x: x.order):
                if og.id == group_id:
                    continue
                for c in sorted(og.configs, key=lambda x: x.order):
                    survivor = c
                    break
                if survivor:
                    break
        # Reassign default if any of this group's configs are default
        had_default = any(c.is_default for c in g.configs)
        had_super = any(c.id == self.super_primary_id for c in g.configs)
        had_primary = any(c.is_primary for c in g.configs)
        any_other_primary = any(c.is_primary for c in survivor_configs)
        self.groups.remove(g)
        if survivor:
            if had_default:
                survivor.is_default = True
            if had_super:
                self.shared["super_primary_config_id"] = survivor.id
                survivor.mark_dirty()
            if had_primary and not any_other_primary:
                survivor.is_primary = True
        else:
            self.shared["super_primary_config_id"] = None
        self._index_dirty = True
        # Final invariant check
        self._validate_invariants(repair=True)

    def rename_group(self, group_id: str, name: str) -> None:
        g = self.find_group(group_id)
        if g is None:
            raise KeyError(f"Group not found: {group_id}")
        g.name = str(name).strip() or g.name
        self._index_dirty = True

    def set_group_capital(self, group_id: str, initial_capital: float) -> None:
        g = self.find_group(group_id)
        if g is None:
            raise KeyError(f"Group not found: {group_id}")
        if initial_capital <= 0:
            raise ValueError("initial_capital must be > 0")
        g.initial_capital = float(initial_capital)
        # Capital change is a structural change — every config in this group
        # needs a state reset on the orchestrator's next sweep.
        for c in g.configs:
            c.mark_dirty()
        self._index_dirty = True

    def reorder_groups(self, order: list[str]) -> None:
        existing = {g.id: g for g in self.groups}
        if set(order) != set(existing.keys()):
            raise ValueError("reorder_groups: id set mismatch")
        for new_idx, gid in enumerate(order):
            existing[gid].order = new_idx
        self._index_dirty = True

    # ----- config CRUD -------------------------------------------------
    def add_config(
        self,
        group_id: str,
        settings: dict[str, Any] | None = None,
        name: str | None = None,
        description: str = "",
    ) -> Config:
        g = self.find_group(group_id)
        if g is None:
            raise KeyError(f"Group not found: {group_id}")
        order = max((c.order for c in g.configs), default=-1) + 1
        if not name:
            name = f"Config {len(g.configs) + 1}"
        c = Config(
            id=_new_id(),
            group_id=g.id,
            name=name,
            description=description,
            is_primary=False,
            is_default=False,
            order=order,
            # Strip shared/group-level keys (total_capital, execution_mode, …)
            # so they can never enter per-config storage via inherited /
            # cloned / pasted settings dicts.
            settings=_strip_per_config(settings or {}),
            _dirty=True,
        )
        # First-ever config across the whole registry → auto-mark default + super-primary
        if not self.all_configs():
            c.is_default = True
            c.is_primary = True
            self.shared["super_primary_config_id"] = c.id
        g.configs.append(c)
        # If this group had no configs and is the only group → also auto-default
        if not self.default_config:
            c.is_default = True
        self._index_dirty = True
        return c

    def remove_config(self, config_id: str) -> None:
        """Remove a config. Auto-reassigns default / super-primary / primary
        to the first surviving config (in registry order) when those flags
        were on the removed config. The frontend warns the operator before
        invoking this so the auto-reassignment is intentional.

        Only blocks when this is the last remaining config (then there's
        nothing to reassign to)."""
        c = self.find_config(config_id)
        if c is None:
            raise KeyError(f"Config not found: {config_id}")
        survivor_configs = [oc for oc in self.all_configs() if oc.id != config_id]
        if not survivor_configs:
            raise ValueError(
                "Cannot remove the only config — at least one must remain."
            )
        # Identify state to reassign post-removal
        was_default = c.is_default
        was_super = c.id == self.super_primary_id
        was_primary = c.is_primary
        any_other_primary = any(oc.is_primary for oc in survivor_configs)
        # Pick survivor: first config of first group in registry order
        survivor: Config | None = None
        for og in sorted(self.groups, key=lambda x: x.order):
            for oc in sorted(og.configs, key=lambda x: x.order):
                if oc.id != config_id:
                    survivor = oc
                    break
            if survivor:
                break
        # Remove from its group
        g = self.find_group_for_config(config_id)
        if g is None:
            raise KeyError(f"Config not found in any group: {config_id}")
        g.configs.remove(c)
        # Reassign flags to survivor
        if survivor:
            if was_default:
                survivor.is_default = True
            if was_super:
                self.shared["super_primary_config_id"] = survivor.id
                survivor.mark_dirty()
            if was_primary and not any_other_primary:
                survivor.is_primary = True
        else:
            # Defensive: shouldn't reach here because we checked survivors above
            self.shared["super_primary_config_id"] = None
        self._index_dirty = True
        # Final invariant check (defensive)
        self._validate_invariants(repair=True)

    def clone_config(
        self,
        config_id: str,
        target_group_id: str | None = None,
        new_name: str | None = None,
    ) -> Config:
        src = self.find_config(config_id)
        if src is None:
            raise KeyError(f"Config not found: {config_id}")
        gid = target_group_id or src.group_id
        clone = self.add_config(
            group_id=gid,
            settings=dict(src.settings),
            name=new_name or f"{src.name} (copy)",
            description=src.description,
        )
        # Clones never inherit primary/default/super-primary flags
        return clone

    def rename_config(
        self, config_id: str, name: str, description: str | None = None
    ) -> None:
        c = self.find_config(config_id)
        if c is None:
            raise KeyError(f"Config not found: {config_id}")
        if name:
            c.name = str(name).strip() or c.name
        if description is not None:
            c.description = str(description)
        self._index_dirty = True

    def reorder_configs(self, group_id: str, order: list[str]) -> None:
        g = self.find_group(group_id)
        if g is None:
            raise KeyError(f"Group not found: {group_id}")
        existing = {c.id: c for c in g.configs}
        if set(order) != set(existing.keys()):
            raise ValueError("reorder_configs: id set mismatch")
        for new_idx, cid in enumerate(order):
            existing[cid].order = new_idx
        self._index_dirty = True

    def move_config(self, config_id: str, target_group_id: str) -> None:
        c = self.find_config(config_id)
        if c is None:
            raise KeyError(f"Config not found: {config_id}")
        src_group = self.find_group_for_config(config_id)
        dst_group = self.find_group(target_group_id)
        if src_group is None or dst_group is None:
            raise KeyError("Group not found")
        if src_group.id == dst_group.id:
            return
        src_group.configs.remove(c)
        c.group_id = dst_group.id
        c.order = max((x.order for x in dst_group.configs), default=-1) + 1
        dst_group.configs.append(c)
        c.mark_dirty()
        self._index_dirty = True

    # ----- flag setters ------------------------------------------------
    def set_primary(self, config_id: str, value: bool) -> None:
        c = self.find_config(config_id)
        if c is None:
            raise KeyError(f"Config not found: {config_id}")
        c.is_primary = bool(value)
        self._index_dirty = True

    def set_default(self, config_id: str) -> None:
        c = self.find_config(config_id)
        if c is None:
            raise KeyError(f"Config not found: {config_id}")
        for other in self.all_configs():
            other.is_default = (other.id == config_id)
        self._index_dirty = True

    def set_super_primary(self, config_id: str) -> None:
        c = self.find_config(config_id)
        if c is None:
            raise KeyError(f"Config not found: {config_id}")
        prev = self.shared.get("super_primary_config_id")
        if prev == config_id:
            return
        self.shared["super_primary_config_id"] = config_id
        # Both old & new super-primary need rebuild — caller (DashboardServer)
        # is responsible for that; we just update the registry.
        if prev:
            prev_cfg = self.find_config(prev)
            if prev_cfg:
                prev_cfg.mark_dirty()
        c.mark_dirty()
        self._index_dirty = True
        logger.info(
            f"[Config] super-primary changed: {prev or '(none)'} → {config_id}"
        )

    # ----- shared settings setters ------------------------------------
    def update_shared(self, key: str, value: Any) -> None:
        if key not in SHARED_KEYS:
            raise KeyError(f"Not a shared key: {key}")
        self.shared[key] = value
        # Execution-mode changes affect the super-primary's components only.
        if key in ("execution_mode", "hedge_execution_mode"):
            sp = self.super_primary_config
            if sp:
                sp.mark_dirty()
        self._index_dirty = True

    # ----- per-config settings setter ---------------------------------
    def update_config_settings(self, config_id: str, settings: dict[str, Any]) -> None:
        """Merge new settings into a config, stripping shared/group-level keys.

        Strips on TWO sides:
        - From the incoming dict (paste payload may carry stale `total_capital`)
        - From the existing dict (a previous bug or legacy import may have
          left `total_capital` lying around — without this side, `update`
          would never remove it because it only adds/replaces keys)

        Without the existing-side strip, a single bad write at any point in
        history poisons the config forever; with it, the next legitimate
        settings update self-heals the entry.
        """
        c = self.find_config(config_id)
        if c is None:
            raise KeyError(f"Config not found: {config_id}")
        for k in list(c.settings.keys()):
            if k in STRIP_FROM_PER_CONFIG:
                del c.settings[k]
        cleaned = _strip_per_config(settings)
        c.settings.update(cleaned)
        c.mark_dirty()
        self._index_dirty = True

    # ----- effective values (force-locks) -----------------------------
    def effective_execution_mode(self, config_id: str) -> str:
        """Return the spot execution mode for a config.

        Only the super-primary may use the shared non-simulation mode. Other
        configs stay simulation-only, so multi-config sessions can compare
        strategies without trying to mirror many simulated portfolios into one
        real/demo exchange account.
        """
        if config_id == self.super_primary_id:
            return str(self.shared.get("execution_mode", "simulation"))
        return "simulation"

    def effective_hedge_mode(self, config_id: str) -> str:
        if config_id == self.super_primary_id:
            return str(self.shared.get("hedge_execution_mode", "simulation"))
        return "simulation"

    # ----- serialization ----------------------------------------------
    def to_settings_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "shared": dict(self.shared),
            "groups": [
                g.to_dict() for g in sorted(self.groups, key=lambda x: x.order)
            ],
        }

    @classmethod
    def from_settings_dict(cls, d: dict[str, Any]) -> "ConfigRegistry":
        shared = dict(d.get("shared", {}))
        groups = [ConfigGroup.from_dict(g) for g in d.get("groups", [])]
        return cls(shared=shared, groups=groups)

    # ----- invariants --------------------------------------------------
    def _validate_invariants(self, repair: bool = False) -> list[str]:
        """Check (and optionally repair) registry invariants:
        - exactly one default when configs exist
        - exactly one super-primary when configs exist
        - super_primary_config_id points to an existing config
        Returns a list of issues found."""
        issues: list[str] = []
        configs = self.all_configs()
        if not configs:
            if self.shared.get("super_primary_config_id"):
                issues.append("super_primary_config_id set but no configs exist")
                if repair:
                    self.shared["super_primary_config_id"] = None
            return issues

        # Default count
        defaults = [c for c in configs if c.is_default]
        if len(defaults) == 0:
            issues.append("no default config")
            if repair:
                configs[0].is_default = True
                logger.warning(f"[Config] No default — auto-assigned {configs[0].id}")
        elif len(defaults) > 1:
            issues.append("multiple default configs")
            if repair:
                for c in defaults[1:]:
                    c.is_default = False
                logger.warning(
                    f"[Config] Multiple defaults — kept {defaults[0].id}, cleared others"
                )

        # Super-primary
        sp_id = self.shared.get("super_primary_config_id")
        if not sp_id or self.find_config(sp_id) is None:
            issues.append(f"super_primary_config_id invalid ({sp_id})")
            if repair:
                fallback = self.default_config or configs[0]
                self.shared["super_primary_config_id"] = fallback.id
                logger.warning(
                    f"[Config] super-primary auto-reassigned to {fallback.id}"
                )

        # Force-lock execution_mode for non-super-primaries (sanity log)
        return issues
