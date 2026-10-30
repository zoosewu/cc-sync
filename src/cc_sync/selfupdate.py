"""cc-sync 自我更新：先更新 marketplace，再以 `claude plugin update` 升到最新版（重啟後生效）。"""
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


def run(claude: Claude) -> dict:
    result = {"action": "update", "ok": False, "updated": False, "from": None, "to": None,
              "error": None, "at": time.time()}
    ok, out = claude("plugin", "marketplace", "update", MARKETPLACE)
    if not ok:
        result["error"] = f"marketplace update failed: {_tail(out)}"
        return result
    ok, out = claude("plugin", "update", PLUGIN_ID, "--json")
    data = _last_json(out)
    if not ok or data is None:
        result["error"] = f"plugin update failed: {_tail(out)}"
        return result
    result["from"], result["to"] = data.get("oldVersion"), data.get("newVersion")
    result["ok"], result["updated"] = True, result["from"] != result["to"]
    return result
