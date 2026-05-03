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


def test_analysis_auto_optimize_page_style() -> None:
    """与队友 demo 默认规模一致：6 井，高级参数可省略（走 schema 默认值）。"""
    payload = {"wells": [{}] * 6}
    response = client.post("/api/analysis/auto-optimize", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("mode") == "page_auto_triple"
    assert "profiles" in body
    for key in ("energy_first", "benefit_first", "balanced"):
        assert key in body["profiles"]
        assert "result" in body["profiles"][key]
    charts = body.get("charts_payload_page") or {}
    assert charts.get("load_curve", {}).get("series")
    assert body.get("recommended_profile") in (None, "energy_first", "benefit_first", "balanced")
    feasible_any = any(
        body["profiles"][k]["result"].get("feasible") for k in ("energy_first", "benefit_first", "balanced")
    )
    assert feasible_any, body.get("notes")
