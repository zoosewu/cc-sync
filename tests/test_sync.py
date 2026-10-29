"""多台機器透過 bare repo 同步的整合測試。"""
OFFICIAL = "claude-plugins-official"


def p(name: str) -> str:
    return f"{name}@{OFFICIAL}"


W1 = {
    "enabledPlugins": {p("context7"): True, p("commit-commands"): True, p("csharp-lsp"): True},
    "language": "繁體中文",
}
L = {
    "enabledPlugins": {p("ralph-loop"): True, p("rust-analyzer-lsp"): True,
                       "herdr-claude-restart@herdr-claude-restart": True},
    "language": "zh-TW",
    "editorMode": "vim",
    "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "bash herdr.sh"}]}]},
}


def installs(m):
    return {c[2] for c in m.claude.calls if c[:2] == ("plugin", "install")}


def uninstalls(m):
    return {c[2] for c in m.claude.calls if c[:2] == ("plugin", "uninstall")}


def test_sync_before_bootstrap_errors(machine):
    r = machine("w1", W1).sync()
    assert not r.ok and "bootstrap" in r.error


def test_seed_then_join_is_union(machine, remote):
    w1, l = machine("w1", W1), machine("l", L, os_name="linux")
    w1.write("skills/shared-skill/SKILL.md", "from w1")
    w1.write("CLAUDE.md", "w1 rules")
    l.write("CLAUDE.md", "l rules")
    l.write("skills/l-skill/SKILL.md", "from l")
    w1.write("skills/synced/bucket/x/SKILL.md", "account synced")

    assert w1.bootstrap(remote).action == "seed"
    r = l.bootstrap(remote)

    assert r.ok and r.action == "join" and r.needs_restart
    assert installs(l) == {p("context7"), p("commit-commands")}  # 只裝遠端有、本機沒有的
    assert uninstalls(l) == set()                                 # 加入只增不刪
    s = l.settings()
    assert s["language"] == "繁體中文"                             # 偏好以 repo 為準
    assert s["editorMode"] == "vim"                               # 本機獨有偏好保留並上傳
    assert s["hooks"] == L["hooks"]                               # 本機 key 不碰
    assert (l.root / "CLAUDE.md").read_text(encoding="utf-8") == "w1 rules"
    assert any("CLAUDE.md" in w for w in r.warnings)
    assert list((l.root / ".cc-sync-backup").rglob("CLAUDE.md"))[0].read_text(encoding="utf-8") == "l rules"
    assert (l.root / "skills/shared-skill/SKILL.md").exists()

    # W1 收到 L 的貢獻；local-only 的 lsp 與 herdr plugin 不傳播
    w1.sync()
    assert installs(w1) == {p("ralph-loop")}
    assert w1.settings()["editorMode"] == "vim"
    assert (w1.root / "skills/l-skill/SKILL.md").exists()
    assert p("rust-analyzer-lsp") not in w1.settings()["enabledPlugins"]


def test_removal_propagates_but_local_only_survives(machine, remote):
    w1, l = machine("w1", W1), machine("l", L, os_name="linux")
    w1.bootstrap(remote)
    l.bootstrap(remote)
    w1.sync()

    l.edit_settings(lambda s: s["enabledPlugins"].pop(p("commit-commands")))
    l.write("skills/中文技能/SKILL.md", "x")
    assert l.sync().committed
    (l.root / "skills/中文技能/SKILL.md").unlink()
    l.sync()

    r = w1.sync()
    assert uninstalls(w1) == {p("commit-commands")}
    assert p("commit-commands") not in w1.settings()["enabledPlugins"]
    assert w1.settings()["enabledPlugins"][p("csharp-lsp")] is True
    assert not (w1.root / "skills/中文技能").exists()
    assert r.needs_restart


def test_disable_propagates_as_disable(machine, remote):
    w1, l = machine("w1", W1), machine("l", L, os_name="linux")
    w1.bootstrap(remote)
    l.bootstrap(remote)
    w1.edit_settings(lambda s: s["enabledPlugins"].__setitem__(p("context7"), False))
    w1.sync()
    l.sync()
    assert ("plugin", "disable", p("context7")) in l.claude.calls
    assert l.settings()["enabledPlugins"][p("context7")] is False


def test_brake_holds_mass_removal_until_forced(machine, remote):
    many = {"enabledPlugins": {p(f"x{i}"): True for i in range(5)}}
    w1, l = machine("w1", many), machine("l", {})
    w1.bootstrap(remote)
    l.bootstrap(remote)

    w1.set_settings({})
    r = w1.sync()
    assert len(r.held) == 5 and not r.committed
    l.sync()
    assert uninstalls(l) == set()

    assert w1.sync(force=True).committed
    l.sync()
    assert uninstalls(l) == {p(f"x{i}") for i in range(5)}


def test_conflict_keeps_local_commit_and_aborts_rebase(machine, remote):
    w1, l = machine("w1", W1), machine("l", L, os_name="linux")
    w1.bootstrap(remote)
    l.bootstrap(remote)
    w1.sync()

    w1.edit_settings(lambda s: s.__setitem__("theme", "dark"))
    l.edit_settings(lambda s: s.__setitem__("theme", "light"))
    assert w1.sync().pushed
    r = l.sync()
    assert not r.ok and "pull failed" in r.error
    assert not (l.root / ".git" / "rebase-merge").exists()
    assert l.settings()["theme"] == "light"


def test_os_specific_skill_is_off_on_windows(machine, remote):
    l, w1 = machine("l", L, os_name="linux"), machine("w1", W1)
    l.write("skills/modern-cli-tools/SKILL.md",
            "---\nname: modern-cli-tools\nmetadata:\n  os: [linux, macos]\n---\nuse rg\n")
    l.write("os/linux.md", "linux only notes")
    l.bootstrap(remote)
    w1.bootstrap(remote)

    assert w1.settings()["skillOverrides"] == {"modern-cli-tools": "off"}
    assert not w1.paths.rules_os.exists()
    assert "skillOverrides" not in l.settings()
    assert l.paths.rules_os.read_text(encoding="utf-8") == "linux only notes"
    # skillOverrides 是本機 key，不得被同步出去
    w1.sync()
    l.sync()
    assert "skillOverrides" not in l.settings()


def test_lock_blocks_concurrent_sync(machine, remote):
    w1 = machine("w1", W1)
    w1.bootstrap(remote)
    w1.paths.lock.write_text("123")
    r = w1.sync()
    assert not r.ok and "running" in r.error
