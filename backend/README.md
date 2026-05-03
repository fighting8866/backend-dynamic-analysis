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

或使用最小联调脚本（需先启动服务）：

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python smoke_test.py --base-url http://127.0.0.1:8000
```

该测试脚本会验证：

- `/api/health`
- `/api/sample-data`
- `/api/analysis/run`
- `/api/analysis/sensitivity`

## 接口说明

### API 列表（总览）

- `GET /health` - 健康检查
- `GET /api/health` - 健康检查（兼容旧版本）
- `GET /api/sample-data` - 获取示例数据
- `POST /api/basic/calculate` - 基础单井优化计算
- `POST /api/advanced/optimize` - 高级井群优化计算
- `POST /api/analysis/run` - 完整分析流程
- `POST /api/analysis/sensitivity` - 敏感性分析
- `GET /api/history` - 获取历史记录
- `DELETE /api/history/{record_id}` - 删除历史记录

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
- `run_request_example`

其中：

- `wells[i].q_it`、`wells[i].e_it` 长度固定为 24
- `scenarios[*].p_s` 概率和约等于 1
- `request_template` 可直接拼装为分析请求
- `run_request_example` 可直接 POST 到 `/api/analysis/run`

### 3. POST `/api/basic/calculate`

用途：基础单井优化计算。

请求体：

```json
{
  "power": 30,
  "output_value": 10,
  "output_unit": "day",
  "electricity_price": 0.65,
  "oil_price": 3500,
  "max_loss_ratio": 5
}
```

参数说明：

- `power`: 抽油机功率 (kW)，必须大于 0
- `output_value`: 油井产量，必须大于 0
- `output_unit`: 产量单位，可选值：`day`、`month`、`year`
- `electricity_price`: 工业电价 (元/kWh)，必须大于 0
- `oil_price`: 原油价格 (元/吨)，必须大于 0
- `max_loss_ratio`: 最大允许产量损失比 (%)，必须在 0-100 之间

返回体：

```json
{
  "best_scheme": "production",
  "schemes": {
    "energy": {
      "name": "节能优先",
      "energy_savings": 36.0,
      "money_saved": 23.4,
      "production_loss": 0.5,
      "loss_rate": 5.0,
      "carbon_reduction": 21.6,
      "net_profit": -1726.6
    },
    "production": {
      "name": "保产优先",
      "energy_savings": 0.36,
      "money_saved": 0.234,
      "production_loss": 0.01,
      "loss_rate": 0.1,
      "carbon_reduction": 0.216,
      "net_profit": -34.766
    },
    "balanced": {
      "name": "平衡方案",
      "energy_savings": 0,
      "money_saved": 0,
      "production_loss": 0,
      "loss_rate": 0,
      "carbon_reduction": 0,
      "net_profit": 0
    }
  }
}
```

### 4. POST `/api/advanced/optimize`

用途：高级井群 24 小时优化计算（6 口井）。

请求体：

```json
{
  "wells": [
    {"id": "W01", "power": 30, "q_rate": 0.5, "startup_cost": 100, "h_min": 4, "h_max": 20},
    {"id": "W02", "power": 40, "q_rate": 0.7, "startup_cost": 120, "h_min": 4, "h_max": 20},
    {"id": "W03", "power": 35, "q_rate": 0.6, "startup_cost": 110, "h_min": 4, "h_max": 20},
    {"id": "W04", "power": 45, "q_rate": 0.8, "startup_cost": 130, "h_min": 4, "h_max": 20},
    {"id": "W05", "power": 50, "q_rate": 0.9, "startup_cost": 140, "h_min": 4, "h_max": 20},
    {"id": "W06", "power": 38, "q_rate": 0.65, "startup_cost": 115, "h_min": 4, "h_max": 20}
  ],
  "params": {
    "oil_price": 3500,
    "carbon_factor": 0.5,
    "transformer_max": 250,
    "q_min": 20,
    "peak_price": 0.8225,
    "flat_price": 0.6277,
    "valley_price": 0.4329,
    "daily_carbon_limit": 1500
  }
}
```

参数说明：

- `wells`: 井参数列表，必须包含 6 口井
  - `id`: 井编号
  - `power`: 额定功率 (kW)
  - `q_rate`: 单位时段产量
  - `startup_cost`: 启动成本
  - `h_min`: 最小运行时长 (小时)
  - `h_max`: 最大运行时长 (小时)
- `params`: 系统参数
  - `oil_price`: 原油价格 (元/吨)
  - `carbon_factor`: 碳排放因子
  - `transformer_max`: 变压器最大容量 (kW)
  - `q_min`: 最低日产量要求
  - `peak_price`: 峰时电价
  - `flat_price`: 平时电价
  - `valley_price`: 谷时电价
  - `daily_carbon_limit`: 日碳排放上限

返回体：

```json
{
  "best_scheme": "benefit",
  "schemes": {
    "energy": {
      "name": "节能优先",
      "total_energy": 数字,
      "total_emission": 数字,
      "total_cost": 数字,
      "revenue": 数字,
      "profit": 数字,
      "total_oil": 数字,
      "peak_load": 数字,
      "total_startups": 数字,
      "load_profile": [24个数字],
      "schedule": [[24个0/1], [24个0/1], ...共6口井]
    },
    "benefit": 同上结构,
    "balanced": 同上结构
  }
}
```

### 5. POST `/api/analysis/run`

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

标准格式（推荐）：

```json
{
  "wells": [
    {
      "well_id": "W01",
      "q_it": [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3],
      "e_it": [8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8],
      "c_start_i": 30,
      "H_min_i": 6,
      "H_max_i": 24,
      "N_max_i": 2
    }
  ],
  "scenarios": [{ "id": "s1", "p_s": 1, "peak_price": 0.9, "offpeak_price": 0.4, "peak_hours": [9, 10, 11] }],
  "gamma_t": [0.42, 0.42, 0.42, 0.42, 0.42, 0.42, 0.42, 0.42, 0.42, 0.42, 0.42, 0.42, 0.42, 0.42, 0.42, 0.42, 0.42, 0.42, 0.42, 0.42, 0.42, 0.42, 0.42, 0.42],
  "weights": { "w_energy": 0.4, "w_carbon": 0.3, "w_economic": 0.3 },
  "Q_min": 3.0
}
```

兼容简化格式（后端会自动标准化）：

```json
{
  "wells": [
    {
      "well_id": "W01",
      "q_it": 0.3,
      "power_consumption": 8,
      "c_start_i": 30,
      "H_min_i": 6,
      "H_max_i": 24,
      "N_max_i": 2
    }
  ],
  "scenarios": [{ "id": "s1", "p_s": 1, "peak_price": 0.9, "offpeak_price": 0.4, "peak_hours": [9, 10, 11] }]
}
```

说明：

- `gamma_t` 可不传，不传时自动读取 demo 值
- `hourly_load_cap` 可不传
- `baseline_compare` 支持 `full_run`、`simple_rule`、`both`
- 标准格式中 `wells[*].q_it` 为长度 24 的数组；若误传单个数字会自动扩展
- 标准格式中 `wells[*].e_it` 为长度 24 的数组；若误传单个数字会自动扩展
- 若未传 `e_it` 但传了 `power_consumption`，后端会自动生成默认 `e_it`
- 若缺少 `weights`，默认使用 `0.4/0.3/0.3`（energy/carbon/economic）
- 若缺少 `Q_min`，默认按理论总产量的 62% 自动估算
- 若缺少 `gamma_t`，默认补样例/默认 24 时段碳排因子

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

- `x_axis`: 井 ID 列表
- `y_axis`: `0:00` 到 `23:00`
- `series`: 热力点数组，元素为 `[wellIndex, hourIndex, value]`

#### `hourly_load`

- `categories`: `0:00..23:00`
- `series`: 折线序列数组（优化/全时运行/固定错峰）

#### `baseline_vs_optimized`

- `categories`: `["总能耗", "总碳排", "期望经济成本"]`
- `series[*].name`: 方案名称
- `series[*].data`: 三指标数组（柱状图）

#### `sensitivity`

- `categories`: 敏感性方案名称
- `series`: 多折线序列（总能耗/总碳排/期望经济成本）

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
