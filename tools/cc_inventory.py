# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Claude Code 環境盤點：輸出 Markdown，貼回對話用。

用法：uv run cc_inventory.py > cc-inventory.md
只讀不寫；env / headers / 疑似 token 一律遮蔽，貼出前仍請自己掃一眼。
"""
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HOME = Path.home()
CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR", HOME / ".claude"))
CLAUDE_JSON = HOME / ".claude.json"

SECRET_KEY = re.compile(r"token|secret|password|passwd|api[_-]?key|auth|bearer|credential|cookie", re.I)
SECRET_VAL = re.compile(r"(sk-[A-Za-z0-9_\-]{8,}|gh[pousr]_[A-Za-z0-9]{8,}|xox[abprs]-[A-Za-z0-9\-]+|AKIA[A-Z0-9]{12,}|eyJ[A-Za-z0-9_\-]{20,})")
# 這些目錄只列名稱與大小，不展開
HEAVY = {"projects", "todos", "shell-snapshots", "statsig", "logs", "cache", "debug", "file-history", "session-env", "ide"}


def redact(obj, parent_key=""):
    if isinstance(obj, dict):
        if parent_key.lower() in {"env", "headers"}:
            return {k: "<redacted>" for k in obj}
        return {k: ("<redacted>" if SECRET_KEY.search(k) and not isinstance(v, (dict, list, bool))
                    else redact(v, k)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v, parent_key) for v in obj]
    if isinstance(obj, str):
        return SECRET_VAL.sub("<redacted>", obj)
    return obj


def run(*argv):
    exe = shutil.which(argv[0])
    if not exe:
        return "(not found)"
    try:
        r = subprocess.run([exe, *argv[1:]], capture_output=True, text=True, timeout=15, encoding="utf-8", errors="replace")
        return (r.stdout or r.stderr).strip() or f"(exit {r.returncode}, no output)"
    except Exception as ex:
        return f"(error: {ex})"


def which_all(name):
    exts = [""] + (os.environ.get("PATHEXT", "").split(";") if os.name == "nt" else [])
    hits = []
    for d in os.environ.get("PATH", "").split(os.pathsep):
        for ext in exts:
            p = Path(d) / (name + ext.lower())
            if p.is_file() and str(p) not in hits:
                hits.append(str(p))
    return hits


def tree_hash(path: Path):
    h = hashlib.sha256()
    files = sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
    for p in files:
        h.update(p.relative_to(path).as_posix().encode() if path.is_dir() else b"")
        h.update(p.read_bytes())
    return h.hexdigest()[:12], len(files)


def size_of(path: Path):
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception as ex:
        return {"<parse error>": str(ex)}


def code(obj, lang="json"):
    body = json.dumps(obj, indent=2, ensure_ascii=False) if lang == "json" else obj
    return f"```{lang}\n{body}\n```"


def section(title):
    print(f"\n## {title}\n")


print(f"# CC inventory — {platform.node()}")

section("System")
for label, val in [
    ("OS", f"{platform.system()} {platform.release()} ({platform.machine()})"),
    ("Python", sys.version.split()[0]),
    ("claude --version", run("claude", "--version")),
    ("uv", run("uv", "--version")),
    ("git", run("git", "--version")),
    ("node", run("node", "--version")),
    ("herdr", run("herdr", "--version")),
    ("SHELL / ComSpec", os.environ.get("SHELL") or os.environ.get("ComSpec", "?")),
    ("CLAUDE_CONFIG_DIR", os.environ.get("CLAUDE_CONFIG_DIR", "(unset)")),
    ("config dir", str(CLAUDE_DIR)),
]:
    print(f"- **{label}**: `{val}`")
print("- **claude on PATH (in order)**:")
for p in which_all("claude") or ["(none)"]:
    print(f"  - `{p}`")

section(f"{CLAUDE_DIR.name}/ top level")
if CLAUDE_DIR.is_dir():
    print("| name | kind | size KB | sha256[:12] / files |\n|---|---|---|---|")
    for p in sorted(CLAUDE_DIR.iterdir(), key=lambda x: x.name.lower()):
        kind = "dir" if p.is_dir() else "file"
        try:
            kb = size_of(p) // 1024
        except Exception:
            kb = "?"
        skip = p.name in HEAVY or p.name in {"plugins", "skills"} or p.name.startswith(".credentials")
        digest = "" if skip else "%s / %d" % tree_hash(p)
        print(f"| {p.name} | {kind} | {kb} | {digest} |")
    git = CLAUDE_DIR / ".git"
    print(f"\n- git repo: {'yes — ' + run('git', '-C', str(CLAUDE_DIR), 'remote', '-v') if git.exists() else 'no'}")
else:
    print("(missing)")

for name in ["settings.json", "settings.local.json", "keybindings.json"]:
    section(name)
    data = load_json(CLAUDE_DIR / name)
    print("(missing)" if data is None else code(redact(data)))

section("CLAUDE.md (user)")
md = CLAUDE_DIR / "CLAUDE.md"
if md.is_file():
    text = md.read_text(encoding="utf-8", errors="replace")
    print(f"- lines: {len(text.splitlines())}, sha256[:12]: `{tree_hash(md)[0]}`")
    heads = [l for l in text.splitlines() if l.startswith("#")]
    print("- headings:\n" + "\n".join(f"  - {h}" for h in heads) if heads else "- headings: (none)")
else:
    print("(missing)")

for sub in ["skills", "agents", "commands", "output-styles", "hooks", "dev-mods"]:
    d = CLAUDE_DIR / sub
    if not d.is_dir():
        continue
    section(f"{sub}/")
    for p in sorted(d.iterdir(), key=lambda x: x.name.lower()):
        link = f" → symlink `{os.readlink(p)}`" if p.is_symlink() else ""
        if sub == "skills" and p.name == "synced":
            # claude.ai 帳號同步的 skills，由 CC 自己管理
            names = sorted(c.name for b in p.iterdir() if b.is_dir() for c in b.iterdir() if c.is_dir())
            print(f"- `synced/` (account-synced by CC){link}: {', '.join(names)}")
            continue
        digest, n = tree_hash(p)
        print(f"- `{p.name}` — {n} file(s), `{digest}`{link}")

section("Plugins")
plugdir = CLAUDE_DIR / "plugins"
for name in ["known_marketplaces.json", "installed_plugins.json", "config.json"]:
    data = load_json(plugdir / name)
    if data is not None:
        print(f"**{name}**\n\n{code(redact(data))}\n")

section("MCP (~/.claude.json)")
cj = load_json(CLAUDE_JSON)
if cj is None:
    print("(missing)")
else:
    print("**user scope mcpServers**\n\n" + code(redact(cj.get("mcpServers", {}))))
    per_proj = {k: sorted(v.get("mcpServers", {})) for k, v in (cj.get("projects") or {}).items()
                if isinstance(v, dict) and v.get("mcpServers")}
    print("\n**local-scope mcpServers per project (names only)**\n\n" + code(per_proj))

section("herdr")
if shutil.which("herdr"):
    print(code(run("herdr", "integration", "status"), "text"))
    cfg = Path(os.environ.get("HERDR_CONFIG_PATH") or (
        Path(os.environ.get("APPDATA", "")) / "herdr/config.toml" if os.name == "nt" else HOME / ".config/herdr/config.toml"))
    print(f"\nconfig `{cfg}`:\n")
    print(code(SECRET_VAL.sub("<redacted>", cfg.read_text(encoding="utf-8")), "toml") if cfg.is_file() else "(missing)")
else:
    print("(not installed)")
