import json

from cc_sync import selfupdate

INSTALLED = json.dumps([
    {"id": "cc-statusline@cc-sync", "version": "0.1.1"},
    {"id": "cc-sync@cc-sync", "version": "0.1.0"},
    {"id": "context7@claude-plugins-official", "version": "1.0.0"},
])


def answer(old: str, new: str) -> str:
    return "noise\n" + json.dumps({"outcome": "ok", "oldVersion": old, "newVersion": new})


def fake(versions: dict[str, tuple[str, str]] | None = None, fail: str | None = None,
         installed: str = INSTALLED):
    """versions: plugin id → (old, new)；fail：含此參數的呼叫失敗。"""
    versions = versions or {}
    calls = []

    def claude(*args: str) -> tuple[bool, str]:
        calls.append(args)
        if fail and fail in args:
            return False, "warn\nnetwork down"
        if args[1] == "list":
            return True, installed
        if args[1] == "update":
            return True, answer(*versions.get(args[2], ("0.1.0", "0.1.0")))
        return True, "done"
    return claude, calls


def test_updates_marketplace_then_every_plugin_of_it():
    claude, calls = fake({"cc-sync@cc-sync": ("0.1.0", "0.1.1"), "cc-statusline@cc-sync": ("0.1.1", "0.1.2")})
    r = selfupdate.run(claude)
    assert calls == [("plugin", "marketplace", "update", "cc-sync"),
                     ("plugin", "list", "--json"),
                     ("plugin", "update", "cc-sync@cc-sync", "--json"),
                     ("plugin", "update", "cc-statusline@cc-sync", "--json")]
    assert r["ok"] and r["updated"] and (r["from"], r["to"]) == ("0.1.0", "0.1.1")
    assert r["plugins"] == [{"id": "cc-sync@cc-sync", "from": "0.1.0", "to": "0.1.1"},
                            {"id": "cc-statusline@cc-sync", "from": "0.1.1", "to": "0.1.2"}]


def test_up_to_date_is_ok_not_updated():
    claude, _ = fake()
    r = selfupdate.run(claude)
    assert r["ok"] and not r["updated"] and r["plugins"] == []


def test_only_another_plugin_updated_still_counts():
    claude, _ = fake({"cc-statusline@cc-sync": ("0.1.1", "0.1.2")})
    r = selfupdate.run(claude)
    assert r["updated"] and r["from"] == r["to"] == "0.1.0"
    assert [p["id"] for p in r["plugins"]] == ["cc-statusline@cc-sync"]


def test_marketplace_failure_skips_plugin_update():
    claude, calls = fake(fail="marketplace")
    r = selfupdate.run(claude)
    assert not r["ok"] and r["error"] == "marketplace update failed: network down"
    assert len(calls) == 1


def test_one_plugin_failing_does_not_stop_the_rest():
    claude, _ = fake({"cc-statusline@cc-sync": ("0.1.1", "0.1.2")}, fail="cc-sync@cc-sync")
    r = selfupdate.run(claude)
    assert not r["ok"] and r["error"] == "cc-sync@cc-sync update failed: network down"
    assert r["updated"] and [p["id"] for p in r["plugins"]] == ["cc-statusline@cc-sync"]


def test_unreadable_list_falls_back_to_cc_sync_alone():
    claude, calls = fake(installed="not json")
    selfupdate.run(claude)
    assert [c[2] for c in calls if c[1] == "update"] == ["cc-sync@cc-sync"]


def test_unparseable_plugin_update_is_failure():
    def claude(*args: str) -> tuple[bool, str]:
        return True, "[]" if args[1] == "list" else "not json"
    r = selfupdate.run(claude)
    assert not r["ok"] and "cc-sync@cc-sync update failed" in r["error"]
