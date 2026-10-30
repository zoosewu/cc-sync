"""同步循環與 bootstrap。"""
import os
import shutil
import socket
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import apply, config, jsonio, os_content, shared
from .gitops import Git, GitError
from .paths import GITATTRIBUTES, GITIGNORE, Paths

STALE_LOCK_SECONDS = 300
NOT_BOOTSTRAPPED = "not bootstrapped: run `/sync init <url>` (or `cc-sync bootstrap <url>`)"


@dataclass
class Result:
    action: str
    ok: bool = True
    committed: bool = False
    pushed: bool = False
    held: list[str] = field(default_factory=list)
    changes: dict = field(default_factory=dict)
    needs_restart: bool = False
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    remote: str | None = None
    at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


class Busy(RuntimeError):
    pass


@contextmanager
def locked(paths: Paths):
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    if paths.lock.exists() and time.time() - paths.lock.stat().st_mtime > STALE_LOCK_SECONDS:
        paths.lock.unlink(missing_ok=True)
    try:
        fd = os.open(paths.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise Busy("another cc-sync is running")
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        paths.lock.unlink(missing_ok=True)


def _host() -> str:
    return socket.gethostname()


def _export_local(paths: Paths, cfg: config.Config) -> shared.Shared:
    exported = shared.export(jsonio.load(paths.settings, {}), cfg)
    shared.write_dir(paths.shared, exported)
    return exported


def _stage(git: Git, cfg: config.Config, force: bool) -> list[str]:
    """git add -A；若刪除量觸發煞車則取消暫存並回傳被擋的路徑。"""
    git.run("add", "-A")
    removed = [l.split("\t", 1)[1] for l in git.lines("diff", "--cached", "--name-status", "--no-renames")
               if l.startswith("D\t")]
    if force or not removed:
        return []
    total = len(git.lines("ls-tree", "-r", "--name-only", "HEAD")) if git.has_head() else 0
    over_count = len(removed) > cfg.brake_max_removals
    over_ratio = len(removed) >= 2 and total > 0 and len(removed) / total >= cfg.brake_max_ratio
    if over_count or over_ratio:
        git.run("reset", "-q")
        return removed
    return []


def _commit(git: Git, message: str) -> bool:
    if not git.has_staged():
        return False
    git.run("commit", "-q", "-m", message)
    return True


def _push(git: Git, result: Result) -> None:
    if git.ahead() == 0:
        return
    r = git.run("push", "-q", check=False)
    if r.returncode == 0:
        result.pushed = True
    else:
        result.warnings.append(f"push failed: {(r.stderr or r.stdout).strip()}")


def _record(paths: Paths, result: Result) -> Result:
    jsonio.write_if_changed(paths.state_dir / "last.json", result.to_dict())
    return result


def sync(paths: Paths, claude: apply.Claude, *, force: bool = False, pull: bool = True,
         push: bool = True, os_name: str | None = None) -> Result:
    os_name = os_name or os_content.current_os()
    result = Result("sync")
    git = Git(paths.root)
    if not git.initialized:
        result.ok, result.error = False, NOT_BOOTSTRAPPED
        return result
    try:
        with locked(paths):
            cfg = config.load(paths.config)
            os_content.apply(paths, os_name)
            before = _export_local(paths, cfg)
            if held := _stage(git, cfg, force):
                result.held = held
                result.warnings.append(f"{len(held)} removals held; run `cc-sync sync --force` to confirm")
                return _record(paths, result)
            result.committed = _commit(git, f"sync: {_host()}")
            if pull and git.has_upstream():
                r = git.run("pull", "-q", "--rebase", "--autostash", check=False)
                if r.returncode != 0:
                    git.run("rebase", "--abort", check=False)
                    result.ok = False
                    result.error = f"pull failed, local commits kept: {(r.stderr or r.stdout).strip()}"
                    return _record(paths, result)
            changes = shared.diff(before, shared.read_dir(paths.shared))
            result.changes = changes.to_dict()
            result.needs_restart = changes.needs_restart
            result.warnings += apply.apply_changes(changes, paths.settings, claude)
            os_content.apply(paths, os_name)
            if push:
                _push(git, result)
    except Busy as e:
        result.ok, result.error = False, str(e)
        return result
    except GitError as e:
        result.ok, result.error = False, str(e)
    return _record(paths, result)


def _backup(paths: Paths, rel: str, stamp: str) -> None:
    src = paths.root / rel
    dst = paths.backup_dir / stamp / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def bootstrap(paths: Paths, url: str, claude: apply.Claude, *, os_name: str | None = None) -> Result:
    """首台播種；其餘以聯集加入（只增不刪，同路徑衝突以 repo 為準並備份本機版本）。"""
    os_name = os_name or os_content.current_os()
    git = Git(paths.root)
    if git.initialized:
        return Result("bootstrap", ok=False, error=f"{paths.root} is already a git repo")
    paths.root.mkdir(parents=True, exist_ok=True)
    try:
        with locked(paths):
            git.run("init", "-q", "-b", "main")
            git.run("remote", "add", "origin", url)
            remote_has_main = bool(git.out("ls-remote", "--heads", "origin", "main"))
            if not remote_has_main:
                result = Result("seed")
                (paths.root / ".gitignore").write_text(GITIGNORE, encoding="utf-8", newline="\n")
                (paths.root / ".gitattributes").write_text(GITATTRIBUTES, encoding="utf-8", newline="\n")
                if not paths.config.exists():
                    jsonio.write_if_changed(paths.config, config.DEFAULTS)
                os_content.apply(paths, os_name)
                _export_local(paths, config.load(paths.config))
                git.run("add", "-A")
                result.committed = _commit(git, f"seed: {_host()}")
                git.run("push", "-q", "-u", "origin", "main")
                result.pushed = True
                return _record(paths, result)

            result = Result("join")
            git.run("fetch", "-q", "origin", "main")
            git.run("reset", "-q", "origin/main")  # HEAD/index = remote，工作樹保持本機
            git.run("branch", "-q", "--set-upstream-to=origin/main")
            stamp = time.strftime("%Y%m%d-%H%M%S")
            for line in git.lines("diff", "--name-status", "--no-renames"):
                status, rel = line.split("\t", 1)
                if status == "M":
                    _backup(paths, rel, stamp)
                    result.warnings.append(f"local {rel} replaced by repo version (backup in .cc-sync-backup/{stamp})")
                git.run("checkout", "--", rel)
            cfg = config.load(paths.config)
            local = shared.export(jsonio.load(paths.settings, {}), cfg)
            merged = shared.union(shared.read_dir(paths.shared), local)
            shared.write_dir(paths.shared, merged)
            changes = shared.diff(local, merged)
            result.changes = changes.to_dict()
            result.needs_restart = changes.needs_restart
            result.warnings += apply.apply_changes(changes, paths.settings, claude)
            os_content.apply(paths, os_name)
            git.run("add", "-A")
            result.committed = _commit(git, f"join: {_host()}")
            _push(git, result)
            return _record(paths, result)
    except (Busy, GitError) as e:
        return Result("bootstrap", ok=False, error=str(e))


def remote(paths: Paths, url: str | None = None) -> Result:
    """顯示或更換同步位置。新位置是空的 → 推上現有資料（搬家）；與本機同源 → 直接改用；
    不相關的歷史 → 拒絕並還原（要加入別的資料 repo 得重新 init）。"""
    result = Result("remote")
    git = Git(paths.root)
    if not git.initialized:
        result.ok, result.error = False, NOT_BOOTSTRAPPED
        return result
    try:
        old = git.out("remote", "get-url", "origin")
        if url is None or url == old:
            result.remote = old
            return result
        with locked(paths):
            git.run("remote", "set-url", "origin", url)
            try:
                if not git.out("ls-remote", "--heads", "origin", "main"):
                    git.run("push", "-q", "-u", "origin", "main")
                    result.pushed = True
                else:
                    git.run("fetch", "-q", "origin", "main")
                    if not git.ok("merge-base", "HEAD", "origin/main"):
                        raise GitError(f"{url} holds unrelated history; to use it, remove "
                                       f"{paths.root / '.git'} and run `/sync init {url}`")
                    git.run("branch", "-q", "--set-upstream-to=origin/main")
            except GitError:
                git.run("remote", "set-url", "origin", old)
                git.run("fetch", "-q", "origin", "main", check=False)
                raise
        result.remote = url
    except (Busy, GitError) as e:
        result.ok, result.error = False, str(e)
    return result
