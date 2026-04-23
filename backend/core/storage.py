"""JSON 文件历史记录存储。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

_lock = Lock()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_all(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"records": []}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # 历史文件损坏时兜底，避免 history 接口直接 500
        return {"records": []}
    if not isinstance(obj, dict):
        return {"records": []}
    records = obj.get("records", [])
    if not isinstance(records, list):
        return {"records": []}
    return {"records": records}


def _write_all(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def append_history(
    history_path: Path,
    *,
    input_summary: dict[str, Any],
    objective_weights: dict[str, float],
    optimized_core_metrics: dict[str, Any],
    explanation_summary: str,
) -> str:
    record_id = str(uuid.uuid4())
    rec = {
        "id": record_id,
        "created_at": _utc_now_iso(),
        "input_summary": input_summary,
        "objective_weights": objective_weights,
        "optimized_core_metrics": optimized_core_metrics,
        "explanation_summary": explanation_summary,
    }
    with _lock:
        data = _read_all(history_path)
        records: list[dict[str, Any]] = data.setdefault("records", [])
        records.insert(0, rec)
        _write_all(history_path, data)
    return record_id


def list_history(history_path: Path) -> list[dict[str, Any]]:
    with _lock:
        return list(_read_all(history_path).get("records", []))


def delete_history(history_path: Path, record_id: str) -> bool:
    with _lock:
        data = _read_all(history_path)
        records: list[dict[str, Any]] = data.get("records", [])
        new_recs = [r for r in records if r.get("id") != record_id]
        if len(new_recs) == len(records):
            return False
        data["records"] = new_recs
        _write_all(history_path, data)
        return True
