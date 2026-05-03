"""新接口测试用例。"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app  # noqa: E402

client = TestClient(app)


def test_health_root() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "oil-pump-optimization-backend"


def test_basic_calculate_normal() -> None:
    payload = {
        "power": 30,
        "output_value": 10,
        "output_unit": "day",
        "electricity_price": 0.65,
        "oil_price": 3500,
        "max_loss_ratio": 5,
    }
    response = client.post("/api/basic/calculate", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert "best_scheme" in body
    assert "schemes" in body
    assert "energy" in body["schemes"]
    assert "production" in body["schemes"]
    assert "balanced" in body["schemes"]


def test_basic_calculate_invalid_output_unit() -> None:
    payload = {
        "power": 30,
        "output_value": 10,
        "output_unit": "invalid",
        "electricity_price": 0.65,
        "oil_price": 3500,
        "max_loss_ratio": 5,
    }
    response = client.post("/api/basic/calculate", json=payload)
    assert response.status_code == 422


def test_basic_calculate_invalid_loss_ratio() -> None:
    payload = {
        "power": 30,
        "output_value": 10,
        "output_unit": "day",
        "electricity_price": 0.65,
        "oil_price": 3500,
        "max_loss_ratio": 101,
    }
    response = client.post("/api/basic/calculate", json=payload)
    assert response.status_code == 422


def test_basic_calculate_negative_power() -> None:
    payload = {
        "power": -10,
        "output_value": 10,
        "output_unit": "day",
        "electricity_price": 0.65,
        "oil_price": 3500,
        "max_loss_ratio": 5,
    }
    response = client.post("/api/basic/calculate", json=payload)
    assert response.status_code == 422


def test_advanced_optimize_normal() -> None:
    payload = {
        "wells": [
            {"id": "W01", "power": 30, "q_rate": 0.5, "startup_cost": 100, "h_min": 4, "h_max": 20},
            {"id": "W02", "power": 40, "q_rate": 0.7, "startup_cost": 120, "h_min": 4, "h_max": 20},
            {"id": "W03", "power": 35, "q_rate": 0.6, "startup_cost": 110, "h_min": 4, "h_max": 20},
            {"id": "W04", "power": 45, "q_rate": 0.8, "startup_cost": 130, "h_min": 4, "h_max": 20},
            {"id": "W05", "power": 50, "q_rate": 0.9, "startup_cost": 140, "h_min": 4, "h_max": 20},
            {"id": "W06", "power": 38, "q_rate": 0.65, "startup_cost": 115, "h_min": 4, "h_max": 20},
        ],
        "params": {
            "oil_price": 3500,
            "carbon_factor": 0.5,
            "transformer_max": 250,
            "q_min": 20,
            "peak_price": 0.8225,
            "flat_price": 0.6277,
            "valley_price": 0.4329,
            "daily_carbon_limit": 1500,
        },
    }
    response = client.post("/api/advanced/optimize", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert "best_scheme" in body
    assert "schemes" in body
    assert "energy" in body["schemes"]
    assert "benefit" in body["schemes"]
    assert "balanced" in body["schemes"]


def test_advanced_optimize_wrong_well_count() -> None:
    payload = {
        "wells": [
            {"id": "W01", "power": 30, "q_rate": 0.5, "startup_cost": 100, "h_min": 4, "h_max": 20},
        ],
        "params": {
            "oil_price": 3500,
            "carbon_factor": 0.5,
            "transformer_max": 250,
            "q_min": 20,
            "peak_price": 0.8225,
            "flat_price": 0.6277,
            "valley_price": 0.4329,
            "daily_carbon_limit": 1500,
        },
    }
    response = client.post("/api/advanced/optimize", json=payload)
    assert response.status_code == 400