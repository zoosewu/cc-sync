"""sync-config.json：三台共用的同步規則。檔案缺的 key 以預設值補齊。"""
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

from . import jsonio

DEFAULTS = {
    "preferenceKeys": [
        "language", "model", "theme", "tui", "editorMode",
        "alwaysThinkingEnabled", "autoMemoryEnabled", "autoUpdatesChannel",
    ],
    "localOnlyPlugins": ["*-lsp@*", "herdr-claude-restart@*", "cc-sync@*"],
    "localOnlyMarketplaces": ["herdr-claude-restart", "cc-sync"],
    "brake": {"maxRemovals": 3, "maxRatio": 0.5},
}


@dataclass(frozen=True)
class Config:
    preference_keys: tuple[str, ...]
    local_only_plugins: tuple[str, ...]
    local_only_marketplaces: tuple[str, ...]
    brake_max_removals: int
    brake_max_ratio: float

    def is_local_plugin(self, plugin_id: str) -> bool:
        return any(fnmatchcase(plugin_id, p) for p in self.local_only_plugins)

    def is_local_marketplace(self, name: str) -> bool:
        return any(fnmatchcase(name, p) for p in self.local_only_marketplaces)


def from_dict(raw: dict) -> Config:
    merged = {**DEFAULTS, **raw}
    brake = {**DEFAULTS["brake"], **merged["brake"]}
    return Config(
        preference_keys=tuple(merged["preferenceKeys"]),
        local_only_plugins=tuple(merged["localOnlyPlugins"]),
        local_only_marketplaces=tuple(merged["localOnlyMarketplaces"]),
        brake_max_removals=int(brake["maxRemovals"]),
        brake_max_ratio=float(brake["maxRatio"]),
    )


def load(path: Path) -> Config:
    return from_dict(jsonio.load(path, {}))
