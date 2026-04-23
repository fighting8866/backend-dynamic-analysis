"""最小自测脚本：验证核心 4 个接口可用。

用法（服务启动后）：
  python smoke_test.py
  python smoke_test.py --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib import error, request


def _http_json(method: str, url: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url=url, method=method, data=data, headers=headers)
    try:
        with request.urlopen(req, timeout=30) as resp:
            status = int(resp.status)
            payload = json.loads(resp.read().decode("utf-8"))
            return status, payload
    except error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="ignore")
        try:
            return int(e.code), json.loads(raw)
        except Exception:
            return int(e.code), {"detail": raw}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    # 1) /api/health
    status, health = _http_json("GET", f"{base}/api/health")
    if status != 200 or health.get("status") != "ok":
        print(f"[FAIL] /api/health: status={status}, body={health}")
        return 1
    print("[PASS] /api/health")

    # 2) /api/sample-data
    status, sample = _http_json("GET", f"{base}/api/sample-data")
    if status != 200:
        print(f"[FAIL] /api/sample-data: status={status}, body={sample}")
        return 1
    wells = sample.get("wells") or []
    scenarios = sample.get("scenarios") or []
    gamma_t = sample.get("gamma_t") or []
    request_template = sample.get("request_template") or {}
    if not wells or not scenarios or len(gamma_t) != 24:
        print("[FAIL] /api/sample-data: 返回字段不完整")
        return 1
    print("[PASS] /api/sample-data")

    # 3) /api/analysis/run
    run_payload = {
        "wells": wells,
        "scenarios": scenarios,
        "gamma_t": gamma_t,
        "weights": request_template.get("weights", {"w_energy": 0.34, "w_carbon": 0.33, "w_economic": 0.33}),
        "Q_min": request_template.get("Q_min", sample.get("recommended_Q_min", 0)),
        "optional_constraints": None,
        "baseline_compare": "both",
    }
    status, run_ret = _http_json("POST", f"{base}/api/analysis/run", run_payload)
    if status != 200 or "optimized_result" not in run_ret:
        print(f"[FAIL] /api/analysis/run: status={status}, body={run_ret}")
        return 1
    print("[PASS] /api/analysis/run")

    # 4) /api/analysis/sensitivity
    sens_payload = {
        "wells": wells,
        "scenarios": scenarios,
        "gamma_t": gamma_t,
        "Q_min": request_template.get("Q_min", sample.get("recommended_Q_min", 0)),
        "optional_constraints": None,
        "weight_sets": None,
    }
    status, sens_ret = _http_json("POST", f"{base}/api/analysis/sensitivity", sens_payload)
    if status != 200 or "cases" not in sens_ret:
        print(f"[FAIL] /api/analysis/sensitivity: status={status}, body={sens_ret}")
        return 1
    print("[PASS] /api/analysis/sensitivity")

    print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
