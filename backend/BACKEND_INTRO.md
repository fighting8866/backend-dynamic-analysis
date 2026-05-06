# 抽油机井群多目标优化系统 — 后端介绍文档

> 本文档面向队友、指导老师与竞赛评委，说明本项目**后端**的职责范围、技术实现与接口约定。前端由队友负责；后端独立完成接口设计、数据校验、优化求解与结构化数据输出，并与前端完成联调。

---

## 一、后端整体作用

后端在系统中承担**计算与数据服务**职责，主要包括：

1. **接收并校验输入**：接收前端提交的抽油机功率、产量、电价、油价、碳相关参数、井群运行约束等；通过 Pydantic 模型进行类型与取值范围校验。
2. **基础单井优化**：在简化假设下，对单井日运行策略进行估算，输出多种目标倾向下的节电、减产、收益等指标（`core/basic_calculator.py`）。
3. **高级井群 24 小时调度**：对固定规模（当前联调为 **6 口井 × 24 时段**）的井群，在分时电价、负荷上限、产量下限、碳排上限等约束下，调用 **OR-Tools（主）/ PuLP（兜底）** 进行混合整数规划类求解，得到开停计划与负荷曲线（`core/optimizer.py`、`core/page_adapter.py`）。
4. **多方案结果**：同时给出**节能优先、效益优先、平衡**等若干套权重下的优化结果，便于对比展示。
5. **结构化输出**：以 JSON 返回指标、24 小时负荷、开停矩阵等，供前端绘制图表、结果卡片及导出（如 Excel）；完整分析流程还可写入历史记录（`data/history.json`），供 `GET /api/history` 查询。

后端**不**负责页面渲染与文件导出逻辑本身，只保证数据字段稳定、含义明确，便于前端消费。

---

## 二、技术栈说明

| 技术 | 作用 |
|------|------|
| **FastAPI** | Web 框架，定义路由、依赖注入与 OpenAPI 文档。 |
| **Uvicorn** | ASGI 服务器，用于本地与部署环境启动服务。 |
| **Pydantic v2** | 请求体 / 响应体建模与自动校验，非法参数返回 **422** 等标准 HTTP 状态。 |
| **OR-Tools** | 井群调度主求解器（混合整数规划相关能力）。 |
| **PuLP** | 在 OR-Tools 不可用或失败时作为求解兜底路径。 |
| **pytest** | 接口与核心路径的自动化测试（`tests/`）。 |
| **CORS 中间件** | 在 `app.py` 中配置跨域，便于浏览器直接打开 `frontend/index.html` 或本地静态服务器访问后端。 |

具体版本约束见 `requirements.txt`；状态汇总见同目录下 `BACKEND_STATUS.md`。

---

## 三、项目结构说明（以仓库实际为准）

```text
you/
  frontend/
    index.html          # 前端单页，已通过 fetch 联调后端
  backend/
    app.py              # FastAPI 应用入口：中间件、路由注册
    requirements.txt    # Python 依赖
    README.md           # 安装、启动、接口总览与协作说明
    BACKEND_STATUS.md   # 后端状态、接口清单与联调说明
    BACKEND_INTRO.md    # 本文档（后端介绍）
    api/
      health.py         # 健康检查（/health、/api/health）
      basic.py          # POST /api/basic/calculate
      advanced.py       # POST /api/advanced/optimize
      analysis.py       # POST /api/analysis/run、sensitivity、auto-optimize
      sample_data.py    # GET /api/sample-data
      history.py        # GET/DELETE 历史记录
    core/
      basic_calculator.py   # 基础单井计算逻辑与请求/响应模型
      optimizer.py          # 井群优化核心（OR-Tools / PuLP）
      page_adapter.py       # 页面参数与优化载荷的适配、三方案编排
      schemas.py            # 分析流程、历史等共用 Pydantic 模型
      baseline.py           # 基准方案与指标封装
      explain.py            # 结果解释辅助
      sensitivity.py        # 敏感性分析
      sample_generator.py   # 示例数据生成
      storage.py            # history.json 读写
      utils.py              # 通用工具函数
    data/
      history.json            # 分析运行历史（由完整分析流程写入）
      scenarios_demo.json 等   # 演示数据
    tests/
      test_smoke.py           # 健康检查、sample-data、analysis、auto-optimize 等
      test_new_endpoints.py   # /health、基础/高级接口及非法参数用例
    smoke_test.py           # 可选：对已启动服务的 HTTP 冒烟脚本
```

说明：`POST /api/advanced/optimize` 在路由层将请求映射为内部的 `AutoOptimizeRequest`，复用 `page_adapter` 与 `optimizer` 的同一套求解链路，保证与「页面级」参数语义一致。

---

## 四、已实现接口说明

### 1. `GET /health`（及 `GET /api/health`）

- **用途**：健康检查，确认服务进程已启动且路由可用。
- **说明**：前端与 `BACKEND_STATUS.md` 中约定根路径 `/health`；`/api/health` 为兼容保留。

### 2. `POST /api/basic/calculate`

- **用途**：**基础单井**优化计算，供「基础单井优化」模块使用。
- **主要输入**（JSON）：
  - `power`：抽油机功率（kW，须大于 0）
  - `output_value`：油井产量
  - `output_unit`：产量单位，仅允许 **`day` / `month` / `year`**
  - `electricity_price`：工业电价（元/kWh，须大于 0）
  - `oil_price`：原油价格（元/吨，须大于 0）
  - `max_loss_ratio`：最大允许产量损失比（**0～100**，单位与业务约定一致）
- **主要输出**：
  - `best_scheme`：在三种方案中推荐的键（`energy` / `production` / `balanced`）
  - `schemes`：三种方案，键为 **`energy`（节能优先）、`production`（保产优先）、`balanced`（平衡方案）**
  - 每个方案包含：`energy_savings`、`money_saved`、`production_loss`、`loss_rate`、`carbon_reduction`、`net_profit` 等（具体见 OpenAPI `/docs` 或 `BasicCalculateResponse`）

### 3. `POST /api/advanced/optimize`

- **用途**：**高级井群** 24 小时调度优化，供「高级井群优化」模块使用。
- **主要输入**：
  - `wells`：**必须为 6 条**，每条含 `id`、`power`、`q_rate`、`startup_cost`、`h_min`、`h_max`（`h_max` ≥ `h_min`，且在 0～24 范围内）
  - `params`：`oil_price`、`carbon_factor`（映射为模型中的碳相关系数）、`transformer_max`（分时总负荷上限）、`q_min`（日最低产量）、`peak_price` / `flat_price` / `valley_price`、`daily_carbon_limit`
- **主要输出**：
  - `best_scheme`：按**净利润**最优在 `energy` / `benefit` / `balanced` 中选优
  - `schemes`：三套方案，每套含 `total_energy`、`total_emission`、`total_cost`、`revenue`、`profit`、`total_oil`、`peak_load`、`total_startups`、`load_profile`（24 点）、`schedule`（6×24 开停矩阵）等
- **错误情况**：井数不为 6 返回 **400**；三方案均无可行解时返回 **400** 及明确 `detail`；参数不合法由 Pydantic 返回 **422**。

### 4. `GET /api/sample-data`

- **用途**：返回演示用井、情景、推荐权重与 `Q_min` 等，便于前端或 `/api/analysis/run` 调试。

### 5. `POST /api/analysis/run`

- **用途**：**完整随机多目标分析流程**（多井分时参数、多情景电价、权重归一化、baseline 对比、解释文案、`charts_payload` 等），运行成功后会追加历史记录。

### 6. `POST /api/analysis/sensitivity`

- **用途**：在给定数据与多组权重下做敏感性扫描，返回多 case 指标与图表占位结构。

### 7. `POST /api/analysis/auto-optimize`（补充）

- **用途**：与页面/demo 对齐的「三权重自动优化」原始 JSON（含 `charts_payload_page` 等），一般供扩展或调试；前端主流程若使用 `POST /api/advanced/optimize`，则以后者返回的精简结构为准。

### 8. `GET /api/history` / `DELETE /api/history/{record_id}`

- **用途**：查询或删除由 **`/api/analysis/run`** 等写入的 JSON 历史记录。

更细的字段说明以 **`http://localhost:8000/docs`** 中的 Swagger 为准。

---

## 五、后端计算逻辑介绍（通俗说明）

1. **基础单井优化**：将用户输入的产量按 `day`/`month`/`year` 换算为**日产量**，在「满发 24 小时」基准下，通过不同的**目标等效减产比例**（在不超过 `max_loss_ratio` 前提下）估算节电量、电费差、产量损失与净收益；碳减排量为与节电量相关的简化折算。三种方案对应不同的减产策略倾向（节能优先贴近上限、保产优先贴近低损失、平衡取中间比例）。
2. **高级井群优化**：将 6 口井的功率、单时段产量、启停成本与运行时长上下限展开为 **24 时段**决策变量，在**峰平谷电价**（映射到逐时电价）、**变压器/母线分时功率上限**、**日最低总产量**、**日碳排上限**以及默认的互斥/夜间禁开/风暴时段等扩展约束下，以加权和形式平衡能耗、碳排与经济成本；同一套数据下用三组权重各求解一次，得到三套可对比方案。
3. **三种方案含义**：节能优先侧重降低能耗与碳相关项；效益最高侧重经济目标；平衡方案使用中间权重，便于汇报与折中决策。

上述为教学/演示向的抽象描述；工业现场还需标定、实测与更多约束，不在当前版本承诺范围内。

---

## 六、参数校验与安全性

- **Pydantic 层**：数值类型、正负、枚举（如 `output_unit`）、`max_loss_ratio` 的 0～100 等均在模型层约束，不合法返回 **422** 与字段级错误信息。
- **业务规则层**：例如高级接口强制 **6 口井**、`h_max` ≥ `h_min`；无可行解时返回 **400** 与可读 `detail`，避免静默返回误导性全零最优。
- **服务稳定性**：求解异常由框架与路由捕获为 HTTP 错误响应，而非导致进程无提示崩溃（仍建议在部署环境配置日志与监控）。

生产环境建议收紧 **CORS** 白名单、增加鉴权与限流（当前为开发联调向配置）。

---

## 七、前后端联调说明

- 前端通过 **`fetch`** 调用后端，默认 **`API_BASE_URL = http://localhost:8000`**（见 `frontend/index.html`）。
- 页面加载或轮询时请求 **`GET /health`**（或等价健康接口）以显示连接状态。
- **「基础单井优化」**：提交表单后请求 **`POST /api/basic/calculate`**。
- **「高级井群优化」**：请求 **`POST /api/advanced/optimize`**，请求体为 6 口井 + `params`。
- 后端统一返回 **JSON**；图表、卡片与 Excel 导出由前端根据返回字段组装。

---

## 八、测试情况

- 已添加自动化测试：`tests/test_smoke.py`（含健康检查、示例数据、完整 `analysis/run`、敏感性、`analysis/auto-optimize` 等路径）、`tests/test_new_endpoints.py`（`/health`、`/api/basic/calculate` 合法与非法用例、`/api/advanced/optimize` 合法与井数错误等）。
- 在依赖安装完整的环境下，执行 `pytest tests/ -v` 可用于回归验证。

---

## 九、启动方式

**安装依赖**（建议在虚拟环境中）：

```powershell
cd backend
python -m pip install -r requirements.txt
```

**启动后端**（仓库根目录若在 `you`，且当前目录为 `backend`）：

```powershell
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

- **接口文档**：浏览器打开 `http://localhost:8000/docs`  
- **健康检查**：`http://localhost:8000/health`

**打开前端**：

- 可直接用浏览器打开项目中的 `frontend/index.html`（与 README 描述一致）；或
- `cd frontend` 后执行 `python -m http.server 5500`，访问 `http://localhost:5500/index.html`（注意与 `index.html` 内配置的 `API_BASE_URL` 一致）。

---

## 十、后续可优化方向

1. **模型与算法**：引入更贴近现场的约束（检修、故障率、泵效曲线等），并对大规模井数做分解或启发式加速。  
2. **数据持久化**：将历史记录从 JSON 文件迁移到数据库，支持分页与检索。  
3. **安全与多用户**：登录鉴权、角色权限、接口限流与审计日志。  
4. **测试与质量**：补充边界用例、性能测试与 CI 流水线。  
5. **部署**：提供 Docker Compose、环境变量配置与健康检查探针。  
6. **可观测性**：结构化日志、请求 ID、求解耗时指标。  
7. **参数模板**：预置真实油田脱敏参数包，一键导入演示。

---

## 附录：汇报口述版（约 1 分钟）

各位老师、评委、队友好。我负责的是本项目的**后端**部分。

系统主题是抽油机井群的**多目标优化和节能收益测算**。前端负责界面和图表，我这边用 **FastAPI** 提供 REST 接口，用 **Pydantic** 做入参校验，用 **OR-Tools 和 PuLP** 做井群 24 小时开停调度求解。

接口上主要有三块：一是 **`GET /health`** 做健康检查；二是 **`POST /api/basic/calculate`**，做**单井**三种方案——节能优先、保产优先和平衡——输出节电、减产、净收益等指标；三是 **`POST /api/advanced/optimize`**，对 **6 口井、24 个小时** 在分时电价、产量下限、碳排上限和变压器容量等约束下求**井群调度**，同样给出节能优先、效益最高和平衡三套结果，包括负荷曲线和开停矩阵，前端用来画图和导出。

另外还有 **`/api/sample-data`** 和完整的 **`/api/analysis/run`** 分析流程、历史记录查询等，方便演示和扩展。

联调上前端用 **fetch** 调本地 **8000** 端口即可。我们写了 **pytest** 用例覆盖正常和非法参数，保证接口稳定返回而不是直接崩掉。

如果后续继续迭代，可以在算法真实度、数据库和部署方面再加强。我的介绍就到这里，谢谢。
