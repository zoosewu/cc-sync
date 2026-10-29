"""把遠端帶來的 Changes 套用到本機：先走 claude CLI，再把 settings.json 校正到同步後的值。"""
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Mapping

from . import jsonio
from .shared import Changes, SectionDiff

# claude(*args) -> (ok, output)
Claude = Callable[..., tuple[bool, str]]

SETTINGS_KEY = {"plugins": "enabledPlugins", "marketplaces": "extraKnownMarketplaces"}


def source_arg(decl: Mapping[str, Any]) -> str | None:
    """extraKnownMarketplaces 的宣告 → `claude plugin marketplace add` 的參數。"""
    src = decl.get("source", {})
    return {"github": src.get("repo"), "git": src.get("url"), "url": src.get("url"),
            "directory": src.get("path"), "file": src.get("path")}.get(src.get("source"))


def _apply_section(target: dict, d: SectionDiff) -> dict:
    out = {**target, **d.added, **d.changed}
    for k in d.removed:
        out.pop(k, None)
    return out


def enforce(settings: Mapping[str, Any], changes: Changes) -> dict:
    """純函式：settings 套上 changes 後的樣子；只動 changes 提到的項目。"""
    out = deepcopy(dict(settings))
    for section, key in SETTINGS_KEY.items():
        d: SectionDiff = getattr(changes, section)
        if not d:
            continue
        merged = _apply_section(out.get(key, {}), d)
        if merged:
            out[key] = merged
        else:
            out.pop(key, None)
    return _apply_section(out, changes.preferences)


def apply_changes(changes: Changes, settings_path: Path, claude: Claude) -> list[str]:
    warnings: list[str] = []

    def call(*args: str) -> None:
        ok, output = claude(*args)
        if not ok:
            warnings.append(f"claude {' '.join(args)} failed: {output}")

    for name, decl in changes.marketplaces.added.items():
        if arg := source_arg(decl):
            call("plugin", "marketplace", "add", arg)
        else:
            warnings.append(f"marketplace {name}: unknown source {decl!r}")
    for pid, value in changes.plugins.added.items():
        call("plugin", "install", pid)
        if value is False:
            call("plugin", "disable", pid)
    for pid, value in changes.plugins.changed.items():
        call("plugin", "enable" if value else "disable", pid)
    for pid in changes.plugins.removed:
        call("plugin", "uninstall", pid)
    for name in changes.marketplaces.removed:
        call("plugin", "marketplace", "remove", name)

    # CLI 可能已改寫 settings.json；重讀後校正，CLI 失敗時設定仍與 repo 一致
    if changes:
        settings = jsonio.load(settings_path, {})
        jsonio.write_if_changed(settings_path, enforce(settings, changes), sort_keys=False)
    return warnings
