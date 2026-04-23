# 发给前端同学的交付说明

本文档用于远程联调：**后端服务契约、示例请求、返回字段与图表数据**。若与 Swagger（`/docs`）不一致，以 **Swagger 与源码中的 Pydantic 模型** 为准。

---

## 1. 后端项目名称

**抽油机井群随机多目标动态分析后端 V1**（仓库内目录：`backend/`，FastAPI + OR-Tools）

---

## 2. 启动命令

在 **`backend`** 目录下（建议先建虚拟环境）：

```bash
python -m venv .venv
```

**Windows PowerShell 激活：**

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

默认监听 **`0.0.0.0:8000`**，前端将 `BASE_URL` 配为 `http://<主机>:8000` 即可。

---

## 3. Swagger 地址

| 说明 | URL |
|------|-----|
| Swagger UI | `http://127.0.0.1:8000/docs` |
| OpenAPI JSON | `http://127.0.0.1:8000/openapi.json` |
| ReDoc | `http://127.0.0.1:8000/redoc` |

---

## 4. 已完成接口列表

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/sample-data` | 拉取 10 井 × 24 时段 demo 数据 + 推荐参数模板 |
| `POST` | `/api/analysis/run` | 完整分析（优化 + 基准 + 对比 + 解释 + 图表 + 历史） |
| `POST` | `/api/analysis/sensitivity` | 仅敏感性（多组权重扫描） |
| `GET` | `/api/history` | 分析历史列表 |
| `DELETE` | `/api/history/{record_id}` | 删除一条历史 |

---

## 5. 每个接口的请求示例

### 5.1 `GET /api/health`

无需请求体。

```http
GET /api/health
```

---

### 5.2 `GET /api/sample-data`

无需请求体。

```http
GET /api/sample-data
```

---

### 5.3 `POST /api/analysis/run`

**Content-Type:** `application/json`

**推荐拼装方式：**先 `GET /api/sample-data`，将返回中的 `wells`、`scenarios`、`gamma_t` 与 `request_template` 合并为一次 `POST` 体（`request_template` 内含推荐 `weights`、`Q_min` 等）。

**最小可行示例结构：**

```json
{
  "wells": [ /* 来自 sample-data，每口井见下文字段说明 */ ],
  "scenarios": [ /* 来自 sample-data；各情景 p_s 之和须约等于 1 */ ],
  "gamma_t": [ /* 可选；缺省则后端从本地样例文件读取 */ ],
  "weights": { "w_energy": 0.34, "w_carbon": 0.33, "w_economic": 0.33 },
  "Q_min": 0,
  "optional_constraints": null,
  "baseline_compare": "both"
}
```

说明：

- `wells`：数组元素须符合 `WellInput`（见第 6 节）。
- `scenarios`：须符合 `ScenarioInput`；**所有 `p_s` 之和与 1 的偏差 ≤ 0.001**。
- `weights`：三项均 ≥ 0，且 **和 > 0**（服务端会再做归一化用于展示与解释）。
- `Q_min`：24h 最低总产量；样例接口会返回 **`recommended_Q_min`**（约为全时产量的 62%），可直接使用以降低不可行概率。
- `baseline_compare`：`"full_run"` | `"simple_rule"` | `"both"`，控制 `baseline_results` 里包含哪些基准（图表里仍会算全时/错峰曲线供对比，与该项无关）。

---

### 5.4 `POST /api/analysis/sensitivity`

```json
{
  "wells": [ /* 同 run */ ],
  "scenarios": [ /* 同 run */ ],
  "gamma_t": null,
  "Q_min": 0,
  "optional_constraints": null,
  "weight_sets": null
}
```

- `weight_sets` 为 **`null` 或省略**：使用后端内置四组模板（节能 / 降碳 / 经济 / 平衡）。
- 若传自定义数组，每项为 `{ "w_energy", "w_carbon", "w_economic" }`，标签为「自定义1」「自定义2」…

---

### 5.5 `GET /api/history`

```http
GET /api/history
```

---

### 5.6 `DELETE /api/history/{record_id}`

```http
DELETE /api/history/550e8400-e29b-41d4-a716-446655440000
```

---

## 6. 每个接口的返回字段说明

### 6.1 `GET /api/health`

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | 如 `"ok"` |
| `service` | string | 服务标识名 |
| `version` | string | 版本号 |

---

### 6.2 `GET /api/sample-data`

| 字段 | 类型 | 说明 |
|------|------|------|
| `meta` | object | 含 `seed`、`num_wells`、`num_slots`、`peak_hours` 等 |
| `wells` | array | 井列表，结构同 `WellInput` |
| `scenarios` | array | 电价情景列表，结构同 `ScenarioInput` |
| `gamma_t` | number[24] | 分时段碳排因子 |
| `recommended_weights` | object | 推荐权重（三字段） |
| `recommended_Q_min` | number | 推荐产量下限（便于一次跑通） |
| `request_template` | object | 含 `weights`、`Q_min`、`optional_constraints`，可与 `wells`/`scenarios`/`gamma_t` 拼成 `POST /api/analysis/run` |

**单井 `wells[]` 主要字段：**

| 字段 | 说明 |
|------|------|
| `well_id` | 井编号字符串 |
| `name` | 可选展示名 |
| `q_it` | 长度 **24** 的时段产量 |
| `e_it` | 长度 **24** 的时段耗电 |
| `c_start_i` | 启动成本 |
| `H_min_i` / `H_max_i` | 单井 24h 内运行时段数上下限（0–24） |
| `N_max_i` | 最大启动次数 |

**单情景 `scenarios[]` 主要字段：**

| 字段 | 说明 |
|------|------|
| `id` | 情景 id |
| `label` | 可选 |
| `p_s` | 概率 (0,1] |
| `peak_price` / `offpeak_price` | 峰 / 非峰电价 |
| `peak_hours` | 峰时段小时列表，元素 ∈ [0,23] |

---

### 6.3 `POST /api/analysis/run`

顶层字段：

| 字段 | 说明 |
|------|------|
| `input_summary` | 井数、时段数、`Q_min`、权重原值与归一化、可选约束、情景概率和等 |
| `optimized_result` | 优化解及指标（见下「指标块」） |
| `baseline_results` | 键为 `baseline_full_run` / `baseline_simple_rule`（由 `baseline_compare` 决定子集） |
| `comparison_summary` | 含 `vs_baseline_full_run`；当基准含错峰时另有 `vs_baseline_simple_rule` |
| `explanation` | 规则解释器输出（中文段落 + 结构化列表） |
| `charts_payload` | 前端图表专用数据（见第 7 节） |
| `saved_record_id` | 本次写入历史的 UUID |
| `sensitivity_preview` | 内置四模板敏感性摘要（`cases`、`templates_meta`、`best_case_label`、`feasible_case_count`） |

**`optimized_result` / 基准结果中「指标块」常用字段：**

| 字段 | 说明 |
|------|------|
| `feasible` | 是否可行 |
| `infeasible_reason` | 不可行时原因文案 |
| `schedule_matrix` | `井索引 × 24` 的 0/1 运行矩阵 |
| `startup_matrix` | `井索引 × 24` 的 0/1 启动矩阵 |
| `total_energy` | 总能耗（运行段耗电合计，与后端模型一致） |
| `total_carbon` | 总碳排 |
| `expected_economic_cost` | 期望综合经济成本 |
| `objective_score` | 归一化加权后的标量目标（可行时一般有值） |
| `total_production` | 总产量 |
| `hourly_load` | 长度 24 的分时总负荷 |
| `normalized_terms` | 归一化分项、锚点、归一化权重等（可选展示） |
| `solver_status` / `solver_engine` / `objective_value_scaled` / `diagnostics` | 求解器诊断（联调可选） |

**`comparison_summary.vs_baseline_full_run`（及错峰键）：**

| 字段 | 说明 |
|------|------|
| `energy_saving_rate` | 相对全时：能耗改善率（越小越好类指标） |
| `carbon_reduction_rate` | 碳排改善率 |
| `economic_improvement_rate` | 期望成本改善率 |
| `production_change_rate` | **产量变化率** \((P_{opt}-P_{base})/P_{base}\)，可为负 |

**`explanation` 主要字段：**

| 字段 | 说明 |
|------|------|
| `dominant_objective` | 当前权重下更偏向的目标描述 |
| `wells_suggested_avoid_peak` | 建议峰段少开的井 id 列表 |
| `wells_better_continuous` | 更适合连续运行的井 |
| `wells_start_stop_limited` | 启停约束偏紧的井 |
| `largest_benefit_vs_full_run` | 相对全时基准的最大收益维度简述 |
| `rule_hits` | 规则命中条目（含 `rule`、`wells`、`message`） |
| `paragraphs` | 多段说明文字 |
| `management_briefing` | 给调度的一句管理建议 |
| `summary_one_line` | 单行摘要（历史记录里也会存） |
| `sensitivity_note` | 与敏感性相关的附注，可为 null |

---

### 6.4 `POST /api/analysis/sensitivity`

| 字段 | 说明 |
|------|------|
| `cases` | 多组权重下每组 `label`、`weights`、可行性与核心指标 |
| `templates_meta` | 使用内置模板时返回模板元数据；自定义权重时为 `null` |
| `best_case_label` | 可行解中 `objective_score` 最小者标签；无可行则为 `null` |
| `feasible_case_count` | 可行方案个数 |

单条 `cases[]`：`label`、`weights`、`feasible`、`infeasible_reason`、`total_energy`、`total_carbon`、`expected_economic_cost`、`objective_score`、`total_production`、`solver_engine` 等。

---

### 6.5 `GET /api/history`

| 字段 | 说明 |
|------|------|
| `records` | 历史数组，新记录在前 |

单条 `records[]`：`id`、`created_at`、`input_summary`、`objective_weights`、`optimized_core_metrics`、`explanation_summary`。

---

### 6.6 `DELETE /api/history/{record_id}`

| 字段 | 说明 |
|------|------|
| `deleted` | 固定 `true` |
| `id` | 被删记录 id |

不存在时：**HTTP 404**，body 为 FastAPI 默认错误结构。

---

## 7. `charts_payload` 字段说明

`POST /api/analysis/run` 返回的 `charts_payload` 专为可视化准备。

### 7.1 `heatmap`

| 字段 | 说明 |
|------|------|
| `x_labels` | 井 id 列表，与 `wells` 顺序一致 |
| `y_labels` | 时段标签，如 `"0:00"` … `"23:00"` |
| `values` | 与 `optimized_result.schedule_matrix` 相同的二维 0/1 |
| `value_label` | 图例说明文案 |

### 7.2 `hourly_load`

| 字段 | 说明 |
|------|------|
| `hours` | `0`–`23` |
| `optimized` | 优化方案 24 点总负荷 |
| `baseline_full_run` | 全时运行 24 点总负荷 |
| `baseline_simple_rule` | 固定错峰 24 点总负荷 |

### 7.3 `baseline_vs_optimized`

| 字段 | 说明 |
|------|------|
| `categories` | 固定三项：`总能耗`、`总碳排`、`期望经济成本` |
| `series` | 多条 `{ "name", "values" }`，含「优化方案」「全时运行」「固定错峰」 |

`values` 与 `categories` 顺序一一对应。

### 7.4 `sensitivity_line`

| 字段 | 说明 |
|------|------|
| `labels` | 各敏感性方案名称（与 `sensitivity_preview.cases` 对齐） |
| `series.total_energy` | 每组总能耗 |
| `series.total_carbon` | 每组总碳排 |
| `series.expected_economic_cost` | 每组期望成本 |

### 7.5 `summary_cards`

便于做 KPI 卡片：每项含 `key`、`label`、`value`、`unit`（如优化总能耗/碳排/期望成本/总产量）。**单位字符串为展示用**，与业务真实单位约定以后端/业务文档为准。

---

## 8. 前端最少需要接哪些字段就能先跑起来

**联调最小闭环（建议顺序）：**

1. **`GET /api/health`** → 确认 `status === "ok"`。
2. **`GET /api/sample-data`** → 缓存 `wells`、`scenarios`、`gamma_t`（可选）、`request_template`。
3. **`POST /api/analysis/run`** → 请求体 = `{ wells, scenarios, gamma_t?, ...request_template }`，并视需要设 `baseline_compare`。
4. 响应中**至少解析**：
   - **`optimized_result.feasible`** + **`infeasible_reason`**：先区分成功/失败；
   - **`optimized_result.schedule_matrix`** 或 **`charts_payload.heatmap.values`**：一张运行图；
   - **`charts_payload.hourly_load`**：一条负荷曲线；
   - **`explanation.summary_one_line` 或 `paragraphs`**：一句话/简短结论。

有精力再接：`comparison_summary`、`charts_payload.baseline_vs_optimized`、`sensitivity_preview`、`GET /api/history`。

---

## 9. 当前后端已知限制

- **规模固定为 demo**：当前样例为 **10 井 × 24 时段**；过大模型求解时间未做产品级保证。
- **422 校验**：`wells`/`scenarios`/`gamma_t` 长度与数值约束不通过时，FastAPI 返回 **422**，前端需统一处理错误体。
- **情景概率**：`scenarios[].p_s` 之和须 **约等于 1**（误差 ≤ 0.001），否则请求被拒。
- **不可行解**：`feasible === false` 时矩阵可能全 0，图表仍以返回结构为准，**勿假设必有可行解**。
- **`Q_min` 过紧**：产量下限、分时负荷上限、启停与时长约束同时偏紧时，易出现无可行解。
- **解释器为规则版**：非大模型生成，**不保证覆盖所有业务语义**，仅作调度参考。
- **历史存储**：默认 **本地 JSON 文件**，无鉴权；多实例部署时**不会自动合并**历史。
- **单位与货币**：金额/产量等为 **演示量纲**，若需真实单位需后续与业务对齐并在接口契约中固化。

---

## 10. 后续可扩展点

- **鉴权**：API Key / JWT、按租户隔离历史与数据目录。
- **持久化**：历史改为 PostgreSQL / SQLite，支持分页、筛选与导出。
- **任务队列**：长耗时求解走 Celery/RQ，接口改为异步 `job_id` 轮询。
- **模型扩展**：多日电量、储能、管网约束、机组组合等；或切换 MIP 引擎与松弛策略。
- **真正多目标**：帕累托前沿、ε-约束法等，而非单一标量化目标。
- **解释增强**：接入内部 LLM 或模板引擎，仍不接外网也可做 richer narrative。
- **配置化**：峰时、`NUM_SLOTS`、求解时间上限等通过环境变量或管理端配置。
- **CSV 导入**：已有 `wells_demo_hourly.csv` 样例，可增加上传解析接口与校验报告。

---

**文档版本：** 与后端 `app.version` / `README` 中 V1 对齐。联调问题请携带：请求 JSON（脱敏）、响应状态码、`optimized_result.infeasible_reason`（若有）。
