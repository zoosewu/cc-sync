import json

from cc_sync import os_content
from cc_sync.paths import Paths

LINUX_SKILL = """---
name: modern-cli-tools
description: x
metadata:
  os: [linux, macos]
---
body
"""


def test_plan_overrides_turns_off_foreign_skills():
    out, managed = os_content.plan_overrides({}, set(), {"mct": ("linux", "macos")}, "windows")
    assert out == {"mct": "off"} and managed == {"mct"}


def test_plan_overrides_restores_when_os_matches():
    out, managed = os_content.plan_overrides({"mct": "off"}, {"mct"}, {"mct": ("linux",)}, "linux")
    assert out == {} and managed == set()


def test_plan_overrides_respects_manual_settings():
    out, managed = os_content.plan_overrides({"mct": "name-only", "other": "off"}, set(),
                                             {"mct": ("linux",)}, "windows")
    assert out == {"mct": "name-only", "other": "off"} and managed == set()


def test_plan_overrides_drops_managed_skill_that_disappeared():
    out, managed = os_content.plan_overrides({"gone": "off"}, {"gone"}, {}, "windows")
    assert out == {} and managed == set()


def test_apply_end_to_end(tmp_path):
    paths = Paths(tmp_path)
    paths.settings.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
    (tmp_path / "skills" / "modern-cli-tools").mkdir(parents=True)
    (tmp_path / "skills" / "modern-cli-tools" / "SKILL.md").write_text(LINUX_SKILL, encoding="utf-8")
    (tmp_path / "os").mkdir()
    (tmp_path / "os" / "linux.md").write_text("use rg", encoding="utf-8")

    os_content.apply(paths, "windows")
    assert json.loads(paths.settings.read_text(encoding="utf-8"))["skillOverrides"] == {"modern-cli-tools": "off"}
    assert not paths.rules_os.exists()

    os_content.apply(paths, "linux")
    assert "skillOverrides" not in json.loads(paths.settings.read_text(encoding="utf-8"))
    assert paths.rules_os.read_text(encoding="utf-8") == "use rg"
