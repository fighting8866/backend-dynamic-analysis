# 抽油机井群随机多目标动态分析后端

## 项目简介

可直接交付联调的 FastAPI 后端，包含：

- FastAPI 接口层
- Pydantic 入参/出参 schema
- OR-Tools 主求解 + PuLP 兜底
- demo 数据生成与加载
- baseline / sensitivity / explain 模块
- JSON history 持久化
- 前端可直接消费的 `charts_payload`
- 最小接口级 smoke test

## 项目结构

```text
backend/
  app.py
  api/
    analysis.py
    health.py
    history.py
    sample_data.py
  core/
    baseline.py
    explain.py
    optimizer.py
    sample_generator.py
    schemas.py
    sensitivity.py
    storage.py
    utils.py
  data/
    history.json
    scenarios_demo.json
    wells_demo.json
    wells_demo_hourly.csv
  tests/
    test_smoke.py
  requirements.txt
  README.md
```

## 安装依赖命令

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 启动后端命令

```powershell
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

启动后可访问：

- Swagger: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/api/health`

## 本地测试方式

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest tests\test_smoke.py -q
```

该测试脚本会验证：

- `/api/health`
- `/api/sample-data`
- `/api/analysis/run`
- `/api/analysis/sensitivity`

## 接口说明

### API 列表（总览）

- `GET /api/health`
- `GET /api/sample-data`
- `POST /api/analysis/run`
- `POST /api/analysis/sensitivity`
- `GET /api/history`
- `DELETE /api/history/{record_id}`

### 1. GET `/api/health`

用途：健康检查。

返回字段：

- `status`
- `service`
- `version`

### 2. GET `/api/sample-data`

用途：生成并返回 demo 数据，同时给前端一份可直接发起分析请求的模板。

返回字段：

- `meta`
- `wells`
- `scenarios`
- `gamma_t`
- `recommended_weights`
- `recommended_Q_min`
- `request_template`

其中：

- `wells[i].q_it`、`wells[i].e_it` 长度固定为 24
- `scenarios[*].p_s` 概率和约等于 1
- `request_template` 可直接拼装为分析请求

### 3. POST `/api/analysis/run`

用途：执行完整分析流程。

请求体：

```json
{
  "wells": [],
  "scenarios": [],
  "gamma_t": [],
  "weights": {
    "w_energy": 0.34,
    "w_carbon": 0.33,
    "w_economic": 0.33
  },
  "Q_min": 0,
  "optional_constraints": {
    "hourly_load_cap": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
  },
  "baseline_compare": "both"
}
```

说明：

- `gamma_t` 可不传，不传时自动读取 demo 值
- `hourly_load_cap` 可不传
- `baseline_compare` 支持 `full_run`、`simple_rule`、`both`

返回字段：

- `input_summary`
- `optimized_result`
- `baseline_results`
- `comparison_summary`
- `explanation`
- `charts_payload`
- `saved_record_id`
- `sensitivity_preview`

`optimized_result` 重点字段：

- `feasible`
- `infeasible_reason`
- `schedule_matrix`
- `startup_matrix`
- `total_energy`
- `total_carbon`
- `expected_economic_cost`
- `objective_score`
- `total_production`
- `hourly_load`
- `normalized_terms`
- `solver_status`
- `solver_engine`
- `diagnostics`

无可行解时：

- 接口仍返回 200
- `optimized_result.feasible = false`
- `optimized_result.infeasible_reason` 给出结构化原因
- `optimized_result.diagnostics` 给出 `Q_min`、理论最大产量、冲突小时等辅助信息

### 4. POST `/api/analysis/sensitivity`

用途：仅做敏感性扫描。

请求体：

```json
{
  "wells": [],
  "scenarios": [],
  "gamma_t": [],
  "Q_min": 0,
  "optional_constraints": {
    "hourly_load_cap": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
  },
  "weight_sets": [
    {
      "w_energy": 0.6,
      "w_carbon": 0.2,
      "w_economic": 0.2
    }
  ]
}
```

返回字段：

- `cases`
- `templates_meta`
- `best_case_label`
- `feasible_case_count`

`cases[*]` 字段：

- `label`
- `weights`
- `feasible`
- `infeasible_reason`
- `total_energy`
- `total_carbon`
- `expected_economic_cost`
- `objective_score`
- `total_production`
- `solver_engine`

### 5. GET `/api/history`

返回：

```json
{
  "records": []
}
```

记录字段：

- `id`
- `created_at`
- `input_summary`
- `objective_weights`
- `optimized_core_metrics`
- `explanation_summary`

### 6. DELETE `/api/history/{record_id}`

成功返回：

```json
{
  "deleted": true,
  "id": "record-id"
}
```

不存在时返回 404。

## 发给前端同学的接口说明

前端联调建议流程：

1. 先调 `/api/sample-data` 获取 `wells`、`scenarios`、`gamma_t` 和推荐参数。
2. 使用返回的 `recommended_weights` 与 `recommended_Q_min` 调 `/api/analysis/run`。
3. 页面图表直接吃 `charts_payload`，列表面板吃 `optimized_result`、`baseline_results`、`comparison_summary`、`explanation`。

### `charts_payload` 字段约定

#### `heatmap`

- `x_labels`: 井 ID 列表
- `y_labels`: `0:00` 到 `23:00`
- `values`: `schedule_matrix`
- `value_label`: `"运行(1)/停机(0)"`

#### `hourly_load`

- `hours`: `0..23`
- `optimized`: 优化方案 24 点总负荷
- `baseline_full_run`: 全时运行基线负荷
- `baseline_simple_rule`: 固定错峰基线负荷

#### `baseline_vs_optimized`

- `categories`: `["总能耗", "总碳排", "期望经济成本"]`
- `series[*].name`: 方案名称
- `series[*].values`: 三指标数组

#### `sensitivity_line`

- `labels`: 敏感性方案名称
- `series.total_energy`
- `series.total_carbon`
- `series.expected_economic_cost`

#### `summary_cards`

可直接做顶部卡片：

- `optimized_energy`
- `optimized_carbon`
- `optimized_cost`
- `optimized_production`

## 求解逻辑说明

- 主求解器：`OR-Tools CP-SAT`
- 兜底求解器：`PuLP CBC`
- 目标：能耗、碳排、期望经济成本三目标加权求最小
- 归一化锚点：`baseline_full_run` 与 `baseline_simple_rule`
- 约束：
  - 最低总产量 `Q_min`
  - 单井最小/最大运行时长
  - 单井最大启停次数
  - 可选分时总负荷上限

## 备注

- 不依赖前端页面即可单独运行
- demo 数据是固定随机种子，可复现
- `history.json` 会自动初始化并持续追加
