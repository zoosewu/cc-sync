"""同步狀態模型：settings.json 的可同步子集。

在 repo 中存成 `shared/<section>/<key>.json`，一項一檔，
讓 git 以檔案為單位三方合併，刪除即刪檔，不會合出壞 JSON。
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from . import jsonio
from .config import Config

SECTIONS = ("plugins", "marketplaces", "preferences")


@dataclass(frozen=True)
class Shared:
    plugins: Mapping[str, Any] = field(default_factory=dict)
    marketplaces: Mapping[str, Any] = field(default_factory=dict)
    preferences: Mapping[str, Any] = field(default_factory=dict)

    def section(self, name: str) -> Mapping[str, Any]:
        return getattr(self, name)


@dataclass(frozen=True)
class SectionDiff:
    added: Mapping[str, Any] = field(default_factory=dict)
    removed: tuple[str, ...] = ()
    changed: Mapping[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.added or self.removed or self.changed)


@dataclass(frozen=True)
class Changes:
    plugins: SectionDiff = SectionDiff()
    marketplaces: SectionDiff = SectionDiff()
    preferences: SectionDiff = SectionDiff()

    def __bool__(self) -> bool:
        return any(getattr(self, s) for s in SECTIONS)

    @property
    def needs_restart(self) -> bool:
        return bool(self.plugins or self.marketplaces)

    def to_dict(self) -> dict:
        return {s: {"added": dict(d.added), "removed": list(d.removed), "changed": dict(d.changed)}
                for s in SECTIONS if (d := getattr(self, s))}


def export(settings: Mapping[str, Any], cfg: Config) -> Shared:
    return Shared(
        plugins={k: v for k, v in settings.get("enabledPlugins", {}).items() if not cfg.is_local_plugin(k)},
        marketplaces={k: v for k, v in settings.get("extraKnownMarketplaces", {}).items()
                      if not cfg.is_local_marketplace(k)},
        preferences={k: settings[k] for k in cfg.preference_keys if k in settings},
    )


def union(remote: Shared, local: Shared) -> Shared:
    """加入時的合併：只增不刪，同 key 以 remote 為準。"""
    return Shared(**{s: {**local.section(s), **remote.section(s)} for s in SECTIONS})


def _diff_section(before: Mapping[str, Any], after: Mapping[str, Any]) -> SectionDiff:
    return SectionDiff(
        added={k: after[k] for k in sorted(after.keys() - before.keys())},
        removed=tuple(sorted(before.keys() - after.keys())),
        changed={k: after[k] for k in sorted(after.keys() & before.keys()) if after[k] != before[k]},
    )


def diff(before: Shared, after: Shared) -> Changes:
    return Changes(**{s: _diff_section(before.section(s), after.section(s)) for s in SECTIONS})


def read_dir(root: Path) -> Shared:
    def read(section: str) -> dict:
        d = root / section
        return {p.stem: jsonio.load(p) for p in sorted(d.glob("*.json"))} if d.is_dir() else {}
    return Shared(**{s: read(s) for s in SECTIONS})


def write_dir(root: Path, shared: Shared) -> None:
    for s in SECTIONS:
        d = root / s
        entries = shared.section(s)
        for key, value in entries.items():
            jsonio.write_if_changed(d / f"{key}.json", value)
        if d.is_dir():
            for p in d.glob("*.json"):
                if p.stem not in entries:
                    p.unlink()
