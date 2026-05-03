"""FastAPI 入口：抽油机井群随机多目标动态分析后端 V1。"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import advanced, analysis, basic, health, history, sample_data

app = FastAPI(
    title="抽油机井群随机多目标动态分析后端",
    description="V1.1：OR-Tools + PuLP 兜底 + 三目标加权和（标准化）+ 情景电价 + 规则解释器",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(basic.router)
app.include_router(advanced.router)
app.include_router(sample_data.router)
app.include_router(analysis.router)
app.include_router(history.router)
