import json

from cc_sync import selfupdate


def fake(update_output: str = "", fail: str | None = None):
    calls = []

    def claude(*args: str) -> tuple[bool, str]:
        calls.append(args)
        if fail and fail in args:
            return False, "warn\nnetwork down"
        return True, update_output if args[1] == "update" else "done"
    return claude, calls


def answer(old: str, new: str) -> str:
    return "noise\n" + json.dumps({"outcome": "ok", "oldVersion": old, "newVersion": new})


def test_updates_marketplace_first_then_plugin():
    claude, calls = fake(answer("0.1.0", "0.1.1"))
    r = selfupdate.run(claude)
    assert calls == [("plugin", "marketplace", "update", "cc-sync"),
                     ("plugin", "update", "cc-sync@cc-sync", "--json")]
    assert r["ok"] and r["updated"] and (r["from"], r["to"]) == ("0.1.0", "0.1.1")


def test_up_to_date_is_ok_not_updated():
    claude, _ = fake(answer("0.1.1", "0.1.1"))
    r = selfupdate.run(claude)
    assert r["ok"] and not r["updated"]


def test_marketplace_failure_skips_plugin_update():
    claude, calls = fake(fail="marketplace")
    r = selfupdate.run(claude)
    assert not r["ok"] and r["error"] == "marketplace update failed: network down"
    assert len(calls) == 1


def test_unparseable_plugin_update_is_failure():
    claude, _ = fake("not json")
    r = selfupdate.run(claude)
    assert not r["ok"] and "plugin update failed" in r["error"]
