"""同步位置（git origin）的查詢與更換。"""
import subprocess

from cc_sync import core


def bare(tmp_path, name: str) -> str:
    path = tmp_path / f"{name}.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(path)], check=True)
    return str(path)


def heads(url: str) -> str:
    return subprocess.run(["git", "ls-remote", "--heads", url, "main"],
                          capture_output=True, text=True, check=True).stdout


def test_remote_before_bootstrap_points_to_init(machine):
    r = core.remote(machine("w1").paths)
    assert not r.ok and "/sync init" in r.error


def test_show_remote(machine, remote):
    w1 = machine("w1")
    w1.bootstrap(remote)
    r = core.remote(w1.paths)
    assert r.ok and r.remote == remote


def test_move_to_empty_repo_pushes_existing_data(machine, remote, tmp_path):
    w1 = machine("w1", {"language": "繁體中文"})
    w1.bootstrap(remote)
    new = bare(tmp_path, "moved")

    r = core.remote(w1.paths, new)
    assert r.ok and r.pushed and r.remote == new
    assert heads(new) == heads(remote)
    w1.edit_settings(lambda s: s.update(theme="dark"))
    assert w1.sync().pushed
    assert heads(new) != heads(remote)  # 之後的同步走新位置


def test_switch_to_mirror_with_shared_history(machine, remote, tmp_path):
    w1 = machine("w1")
    w1.bootstrap(remote)
    mirror = bare(tmp_path, "mirror")
    subprocess.run(["git", "-C", str(w1.root), "push", "-q", mirror, "main"], check=True)

    r = core.remote(w1.paths, mirror)
    assert r.ok and not r.pushed and r.remote == mirror
    assert w1.sync().ok


def test_unrelated_repo_is_refused_and_origin_restored(machine, remote, tmp_path):
    w1, other = machine("w1"), machine("other", {"theme": "light"})
    w1.bootstrap(remote)
    unrelated = bare(tmp_path, "unrelated")
    other.bootstrap(unrelated)

    r = core.remote(w1.paths, unrelated)
    assert not r.ok and "unrelated history" in r.error
    assert core.remote(w1.paths).remote == remote
    assert w1.sync().ok
