# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Claude Code 環境清理。預設 dry-run，只列出計畫。

用法：
  uv run cc_cleanup.py                       # 只列計畫
  uv run cc_cleanup.py --apply               # 執行
  uv run cc_cleanup.py --apply --delete-homunculus   # 連 ECC 殘留資料一起刪

規則：
  1. enabledPlugins 中「啟用但未安裝」的項目 → 從 settings.json 移除
  2. 沒有任何已安裝 plugin 的 marketplace（官方除外）→ claude plugin marketplace remove
  3. REDUNDANT 中列出、與帳號同步 skill 重複的 plugin → claude plugin uninstall
  4. ~/.claude/homunculus（ECC 殘留）→ 僅 --delete-homunculus 時刪除
settings.json 修改前會備份為 settings.json.bak-cleanup-<時間>。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
SETTINGS = CLAUDE_DIR / "settings.json"
PLUGINS = CLAUDE_DIR / "plugins"
KEEP_MARKETPLACES = {"claude-plugins-official"}
REDUNDANT = {"skill-creator@claude-plugins-official"}  # 與 claude.ai 同步的 skill-creator 重複


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def claude(*args):
    exe = shutil.which("claude")
    r = subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout + r.stderr).strip()
    print(f"    $ claude {' '.join(args)} → exit {r.returncode}" + (f"\n      {out}" if out else ""))
    return r.returncode == 0


def plan():
    settings = load(SETTINGS, {})
    installed = set(load(PLUGINS / "installed_plugins.json", {}).get("plugins", {}))
    known = load(PLUGINS / "known_marketplaces.json", {})
    extra = settings.get("extraKnownMarketplaces", {})

    dangling = [p for p in settings.get("enabledPlugins", {})
                if p not in installed and not p.endswith("@skills-dir")]
    used = {p.split("@", 1)[1] for p in installed}
    unused_mp = sorted(m for m in set(known) | set(extra) if m not in used and m not in KEEP_MARKETPLACES)
    redundant = sorted(REDUNDANT & installed)
    homunculus = CLAUDE_DIR / "homunculus"
    return dangling, unused_mp, redundant, homunculus if homunculus.exists() else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--delete-homunculus", action="store_true")
    args = ap.parse_args()

    dangling, unused_mp, redundant, homunculus = plan()
    print(f"# CC cleanup — {CLAUDE_DIR}  ({'APPLY' if args.apply else 'dry-run'})\n")
    print("1. 移除啟用但未安裝的 plugin：", dangling or "（無）")
    print("2. 移除沒有已安裝 plugin 的 marketplace：", unused_mp or "（無）")
    print("3. 解除安裝重複的 plugin：", redundant or "（無）")
    if homunculus:
        gb = sum(p.stat().st_size for p in homunculus.rglob("*") if p.is_file()) / 1024**3
        flag = "會刪除" if args.delete_homunculus else "略過（需 --delete-homunculus）"
        print(f"4. {homunculus}（{gb:.1f} GB）：{flag}")
    else:
        print("4. homunculus：（不存在）")

    if not args.apply:
        print("\n未變更任何東西。確認無誤後加 --apply 執行。")
        return
    if not shutil.which("claude"):
        sys.exit("找不到 claude 指令")

    print()
    for mp in unused_mp:
        claude("plugin", "marketplace", "remove", mp)
    for p in redundant:
        claude("plugin", "uninstall", p)

    # CLI 可能已改寫 settings.json，重新讀取後再處理殘留項
    settings = load(SETTINGS, {})
    enabled = settings.get("enabledPlugins", {})
    extra = settings.get("extraKnownMarketplaces", {})
    stale = [p for p in dangling if p in enabled] + [m for m in unused_mp if m in extra]
    if stale:
        backup = SETTINGS.with_name(f"settings.json.bak-cleanup-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(SETTINGS, backup)
        for p in dangling:
            enabled.pop(p, None)
        for m in unused_mp:
            extra.pop(m, None)
        if not extra:
            settings.pop("extraKnownMarketplaces", None)
        SETTINGS.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"    settings.json 移除 {stale}（備份：{backup.name}）")

    if homunculus and args.delete_homunculus:
        shutil.rmtree(homunculus)
        print(f"    已刪除 {homunculus}")

    print("\n完成。重新執行（不加 --apply）確認計畫已清空；重啟 Claude Code 生效。")


main()
