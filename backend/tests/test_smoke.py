from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app  # noqa: E402


client = TestClient(app)


def _sample_bundle() -> dict:
    response = client.get("/api/sample-data")
    assert response.status_code == 200
    return response.json()


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "1.1.0"


def test_sample_data() -> None:
    bundle = _sample_bundle()
    assert len(bundle["wells"]) == 10
    assert len(bundle["gamma_t"]) == 24
    assert bundle["recommended_Q_min"] > 0
    assert "request_template" in bundle


def test_analysis_run() -> None:
    bundle = _sample_bundle()
    payload = {
        "wells": bundle["wells"],
        "scenarios": bundle["scenarios"],
        "gamma_t": bundle["gamma_t"],
        "weights": bundle["recommended_weights"],
        "Q_min": bundle["recommended_Q_min"],
    }
    response = client.post("/api/analysis/run", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert "optimized_result" in body
    assert "charts_payload" in body
    assert body["optimized_result"]["feasible"] is True
    assert len(body["optimized_result"]["schedule_matrix"]) == len(bundle["wells"])
    assert body["saved_record_id"]


def test_analysis_sensitivity() -> None:
    bundle = _sample_bundle()
    payload = {
        "wells": bundle["wells"],
        "scenarios": bundle["scenarios"],
        "gamma_t": bundle["gamma_t"],
        "Q_min": bundle["recommended_Q_min"],
    }
    response = client.post("/api/analysis/sensitivity", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert "cases" in body
    assert len(body["cases"]) >= 1
    assert body["feasible_case_count"] >= 1
