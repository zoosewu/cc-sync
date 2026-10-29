"""git 指令包裝：永不互動、輸出可解析、缺身分時自動補。"""
import os
import socket
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


class GitError(RuntimeError):
    pass


@dataclass
class Git:
    root: Path
    _identity: list[str] | None = field(default=None, init=False, repr=False)

    def _env(self) -> dict:
        return {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_EDITOR": "true", "LC_ALL": "C"}

    def _raw(self, *args: str) -> subprocess.CompletedProcess:
        # quotePath=false：非 ASCII 檔名原樣輸出，否則 name-status 解析會壞
        return subprocess.run(["git", "-C", str(self.root), "-c", "core.quotePath=false", *args],
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=self._env())

    def identity(self) -> list[str]:
        if self._identity is None:
            has = self._raw("config", "user.email").stdout.strip()
            self._identity = [] if has else [
                "-c", "user.name=cc-sync", "-c", f"user.email=cc-sync@{socket.gethostname()}"]
        return self._identity

    def run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        r = self._raw(*self.identity(), *args)
        if check and r.returncode != 0:
            raise GitError(f"git {' '.join(args)}: {(r.stderr or r.stdout).strip()}")
        return r

    def out(self, *args: str) -> str:
        return self.run(*args).stdout.strip()

    def ok(self, *args: str) -> bool:
        return self.run(*args, check=False).returncode == 0

    def lines(self, *args: str) -> list[str]:
        return [l for l in self.out(*args).splitlines() if l]

    @property
    def initialized(self) -> bool:
        return (self.root / ".git").exists()

    def has_head(self) -> bool:
        return self.ok("rev-parse", "--verify", "-q", "HEAD")

    def has_upstream(self) -> bool:
        return self.ok("rev-parse", "--abbrev-ref", "@{u}")

    def ahead(self) -> int:
        return int(self.out("rev-list", "--count", "@{u}..HEAD")) if self.has_upstream() else 0

    def has_staged(self) -> bool:
        return not self.ok("diff", "--cached", "--quiet")
