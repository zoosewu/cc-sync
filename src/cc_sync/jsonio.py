"""JSON 讀寫：固定格式、原子寫入（settings.json 受 CC 監看，不可寫到一半）。"""
import json
import os
from pathlib import Path
from typing import Any


def dumps(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def load(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".cc-sync-tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def write_if_changed(path: Path, obj: Any, *, sort_keys: bool = True) -> bool:
    text = dumps(obj) if sort_keys else json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    write_atomic(path, text)
    return True
