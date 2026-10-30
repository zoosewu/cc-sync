"""`cc-sync` 指令。輸出一行 JSON 供 mod 解析；`--human` 改為人讀格式。"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from . import core, jsonio, selfupdate
from .paths import Paths, default_root


def claude_cli(*args: str) -> tuple[bool, str]:
    exe = shutil.which("claude")
    if not exe:
        return False, "claude not found on PATH"
    r = subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=300)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def _print(data: dict, human: bool) -> None:
    if not human:
        print(json.dumps(data, ensure_ascii=False))
        return
    for k, v in data.items():
        if v not in (None, [], {}, False):
            print(f"{k}: {json.dumps(v, ensure_ascii=False, indent=2) if isinstance(v, (dict, list)) else v}")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="cc-sync")
    ap.add_argument("--root", help="Claude config dir (default: $CLAUDE_CONFIG_DIR or ~/.claude)")
    ap.add_argument("--human", action="store_true", help="human-readable output")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bootstrap", help="seed or join a sync repo (any git URL you can push to)")
    b.add_argument("url")
    s = sub.add_parser("sync", help="export, commit, pull, apply, push")
    s.add_argument("--force", action="store_true", help="confirm removals held by the brake")
    s.add_argument("--no-pull", action="store_true", help="commit (and push) only")
    s.add_argument("--no-push", action="store_true")
    sub.add_parser("status", help="last sync result")
    r = sub.add_parser("remote", help="show the sync location, or move it to another git URL")
    r.add_argument("url", nargs="?")
    sub.add_parser("update", help="update the cc-sync plugin to the latest version")
    args = ap.parse_args(argv)

    if args.cmd == "update":
        data = selfupdate.run(claude_cli)
        _print(data, args.human)
        return 0 if data["ok"] else 1

    paths = Paths(Path(args.root) if args.root else default_root())
    if args.cmd == "bootstrap":
        result = core.bootstrap(paths, args.url, claude_cli)
    elif args.cmd == "sync":
        result = core.sync(paths, claude_cli, force=args.force, pull=not args.no_pull, push=not args.no_push)
    elif args.cmd == "remote":
        result = core.remote(paths, args.url)
    else:
        _print(jsonio.load(paths.state_dir / "last.json", {"action": "none"}), args.human)
        return 0
    _print(result.to_dict(), args.human)
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
