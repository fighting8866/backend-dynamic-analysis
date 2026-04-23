from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from core.schemas import SampleDataResponse
from core.sample_generator import ensure_demo_files, load_bundle_from_disk

router = APIRouter(tags=["sample-data"])


def _data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


@router.get("/api/sample-data", response_model=SampleDataResponse)
def get_sample_data() -> dict:
    d = _data_dir()
    ensure_demo_files(d)
    return load_bundle_from_disk(d)
