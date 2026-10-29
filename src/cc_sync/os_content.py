"""OS 專屬內容：os/<os>.md → rules/，以及依 skill 的 metadata.os 管理 skillOverrides。"""
import platform
import shutil
from pathlib import Path
from typing import Mapping

import yaml

from . import jsonio
from .paths import Paths

OS_NAMES = {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}


def current_os() -> str:
    return OS_NAMES.get(platform.system(), platform.system().lower())


def sync_rules(paths: Paths, os_name: str) -> None:
    src = paths.os_dir / f"{os_name}.md"
    dst = paths.rules_os
    if src.is_file():
        if not dst.is_file() or dst.read_bytes() != src.read_bytes():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
    elif dst.exists():
        dst.unlink()


def frontmatter(skill_md: Path) -> dict:
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    try:
        data = yaml.safe_load(text[3:end]) if end != -1 else None
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def skill_os_map(skills_dir: Path) -> dict[str, tuple[str, ...]]:
    """skill 名稱 → 允許的 OS；只列出有宣告 metadata.os 的 skill。"""
    out = {}
    for md in sorted(skills_dir.glob("*/SKILL.md")) if skills_dir.is_dir() else []:
        if md.parent.name == "synced":
            continue
        fm = frontmatter(md)
        oses = (fm.get("metadata") or {}).get("os")
        if oses:
            out[str(fm.get("name") or md.parent.name)] = tuple([oses] if isinstance(oses, str) else oses)
    return out


def plan_overrides(overrides: Mapping[str, str], managed: set[str],
                   skill_os: Mapping[str, tuple[str, ...]], os_name: str) -> tuple[dict, set[str]]:
    """純函式：回傳 (新 skillOverrides, 新的受管名單)。使用者手設、非受管的項目不動。"""
    off = {name for name, oses in skill_os.items() if os_name not in oses}
    new_managed = {n for n in off if n in managed or n not in overrides}
    out = dict(overrides)
    for n in managed - new_managed:
        if out.get(n) == "off":
            out.pop(n)
    for n in new_managed:
        out[n] = "off"
    return out, new_managed


def apply(paths: Paths, os_name: str) -> None:
    sync_rules(paths, os_name)
    state = jsonio.load(paths.state, {})
    settings = jsonio.load(paths.settings, {})
    overrides, managed = plan_overrides(settings.get("skillOverrides", {}),
                                        set(state.get("managedSkillOverrides", [])),
                                        skill_os_map(paths.skills), os_name)
    if overrides != settings.get("skillOverrides", {}):
        if overrides:
            settings["skillOverrides"] = overrides
        else:
            settings.pop("skillOverrides", None)
        jsonio.write_if_changed(paths.settings, settings, sort_keys=False)
    state["managedSkillOverrides"] = sorted(managed)
    jsonio.write_if_changed(paths.state, state)
