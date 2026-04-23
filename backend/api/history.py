from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from core.schemas import HistoryDeleteResponse, HistoryListResponse
from core.storage import delete_history, list_history

router = APIRouter(tags=["history"])


def _history_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "history.json"


@router.get("/api/history", response_model=HistoryListResponse)
def get_history() -> dict:
    return {"records": list_history(_history_path())}


@router.delete("/api/history/{record_id}", response_model=HistoryDeleteResponse)
def remove_history(record_id: str) -> dict:
    ok = delete_history(_history_path(), record_id)
    if not ok:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"deleted": True, "id": record_id}
