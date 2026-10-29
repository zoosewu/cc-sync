from cc_sync import config, shared
from cc_sync.apply import enforce, source_arg
from cc_sync.shared import Shared

CFG = config.from_dict({})

SETTINGS = {
    "enabledPlugins": {
        "context7@claude-plugins-official": True,
        "csharp-lsp@claude-plugins-official": True,
        "herdr-claude-restart@herdr-claude-restart": True,
        "ralph-loop@claude-plugins-official": False,
    },
    "extraKnownMarketplaces": {
        "ecc": {"source": {"source": "github", "repo": "a/b"}},
        "herdr-claude-restart": {"source": {"source": "github", "repo": "x/y"}},
    },
    "language": "繁體中文",
    "hooks": {"SessionStart": []},
    "skipDangerousModePermissionPrompt": True,
}


def test_export_keeps_only_shared_parts():
    s = shared.export(SETTINGS, CFG)
    assert s.plugins == {"context7@claude-plugins-official": True, "ralph-loop@claude-plugins-official": False}
    assert list(s.marketplaces) == ["ecc"]
    assert s.preferences == {"language": "繁體中文"}


def test_union_adds_only_and_remote_wins():
    remote = Shared(plugins={"a@m": True}, preferences={"language": "zh-TW"})
    local = Shared(plugins={"a@m": False, "b@m": True}, preferences={"language": "en", "theme": "dark"})
    u = shared.union(remote, local)
    assert u.plugins == {"a@m": True, "b@m": True}
    assert u.preferences == {"language": "zh-TW", "theme": "dark"}


def test_diff():
    before = Shared(plugins={"a@m": True, "b@m": True, "c@m": True})
    after = Shared(plugins={"a@m": True, "b@m": False, "d@m": True})
    d = shared.diff(before, after)
    assert d.plugins.added == {"d@m": True}
    assert d.plugins.removed == ("c@m",)
    assert d.plugins.changed == {"b@m": False}
    assert d.needs_restart
    assert not shared.diff(after, after)


def test_preference_only_diff_needs_no_restart():
    d = shared.diff(Shared(preferences={"theme": "dark"}), Shared(preferences={"theme": "light"}))
    assert d and not d.needs_restart


def test_dir_roundtrip_deletes_stale_entries(tmp_path):
    shared.write_dir(tmp_path, Shared(plugins={"a@m": True, "b@m": True}, preferences={"tui": "fullscreen"}))
    shared.write_dir(tmp_path, Shared(plugins={"a@m": True}))
    assert shared.read_dir(tmp_path) == Shared(plugins={"a@m": True})


def test_enforce_touches_only_changed_entries():
    changes = shared.diff(Shared(plugins={"context7@claude-plugins-official": True}),
                          Shared(plugins={"x@m": True}, preferences={"language": "zh-TW"}))
    out = enforce(SETTINGS, changes)
    assert "context7@claude-plugins-official" not in out["enabledPlugins"]
    assert out["enabledPlugins"]["x@m"] is True
    assert out["enabledPlugins"]["csharp-lsp@claude-plugins-official"] is True  # local-only 不動
    assert out["language"] == "zh-TW"
    assert out["hooks"] == SETTINGS["hooks"]


def test_source_arg():
    assert source_arg({"source": {"source": "github", "repo": "a/b"}}) == "a/b"
    assert source_arg({"source": {"source": "git", "url": "https://x/y.git"}}) == "https://x/y.git"
    assert source_arg({"source": {"source": "weird"}}) is None
