"""~/.claude 內 cc-sync 會碰到的路徑。"""
import os
from dataclasses import dataclass
from pathlib import Path

# cc-sync-data 的白名單：預設全忽略，逐項放行
GITIGNORE = """\
/*
!/.gitignore
!/.gitattributes
!/shared/
!/sync-config.json
!/CLAUDE.md
!/skills/
/skills/synced/
!/agents/
!/commands/
!/os/
"""

GITATTRIBUTES = "* text=auto eol=lf\n"


def default_root() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def settings(self) -> Path:
        return self.root / "settings.json"

    @property
    def shared(self) -> Path:
        return self.root / "shared"

    @property
    def config(self) -> Path:
        return self.root / "sync-config.json"

    @property
    def skills(self) -> Path:
        return self.root / "skills"

    @property
    def os_dir(self) -> Path:
        return self.root / "os"

    @property
    def rules_os(self) -> Path:
        return self.root / "rules" / "cc-sync-os.md"

    @property
    def state_dir(self) -> Path:
        return self.root / ".cc-sync"

    @property
    def state(self) -> Path:
        return self.state_dir / "state.json"

    @property
    def lock(self) -> Path:
        return self.state_dir / "lock"

    @property
    def backup_dir(self) -> Path:
        return self.root / ".cc-sync-backup"
