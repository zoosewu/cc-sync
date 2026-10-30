"""自我更新：先更新 marketplace，再以 `claude plugin update` 把本 marketplace 已安裝的 plugin
（cc-sync、cc-statusline…）升到最新版（重啟後生效）。"""
import json
import time
from typing import Callable

MARKETPLACE = "cc-sync"
PLUGIN_ID = "cc-sync@cc-sync"

# claude(*args) -> (ok, output)
Claude = Callable[..., tuple[bool, str]]


def _last_json(output: str) -> dict | None:
    for line in reversed(output.splitlines()):
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                return None
    return None


def _tail(output: str) -> str:
    lines = output.strip().splitlines()
    return lines[-1] if lines else "no output"


def _installed(claude: Claude) -> list[str]:
    """本 marketplace 已安裝的 plugin id；cc-sync 排最前。讀不到清單就只更新 cc-sync。"""
    ok, out = claude("plugin", "list", "--json")
    try:
        items = json.loads(out) if ok else []
    except json.JSONDecodeError:
        items = []
    ids = {i["id"] for i in items if isinstance(i, dict) and str(i.get("id", "")).endswith(f"@{MARKETPLACE}")}
    return [PLUGIN_ID] + sorted(ids - {PLUGIN_ID})


def run(claude: Claude) -> dict:
    """`from`／`to` 是 cc-sync 本身的版本；`plugins` 列出這次有升版的 plugin。"""
    result = {"action": "update", "ok": False, "updated": False, "from": None, "to": None,
              "plugins": [], "error": None, "at": time.time()}
    ok, out = claude("plugin", "marketplace", "update", MARKETPLACE)
    if not ok:
        result["error"] = f"marketplace update failed: {_tail(out)}"
        return result
    errors = []
    for plugin in _installed(claude):
        ok, out = claude("plugin", "update", plugin, "--json")
        data = _last_json(out)
        if not ok or data is None:
            errors.append(f"{plugin} update failed: {_tail(out)}")
            continue
        old, new = data.get("oldVersion"), data.get("newVersion")
        if plugin == PLUGIN_ID:
            result["from"], result["to"] = old, new
        if old != new:
            result["plugins"].append({"id": plugin, "from": old, "to": new})
    result["ok"], result["updated"] = not errors, bool(result["plugins"])
    result["error"] = "; ".join(errors) or None
    return result
