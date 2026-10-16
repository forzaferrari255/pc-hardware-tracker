# 交付报告

**项目路径**：`/workspace/pc-hardware-tracker/`  
**验证时间**：2026-10-16（Asia/Shanghai）

## 启动命令

```bash
cd /workspace/pc-hardware-tracker
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 可选填 DEEPSEEK_API_KEY
python scripts/seed_demo.py
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

浏览器：http://127.0.0.1:8000  

## 验证结果摘要

| 检查项 | 结果 |
|--------|------|
| seed | products=8, watchlist=3, clean=488, outliers=48（每商品 6 条脏数据均被标 outlier） |
| GET /api/health | ok；FORCE_OFFLINE=1 时 online=false |
| GET /api/watchlist | 含 RTX 5080 16G / R7 9700X / 990 PRO 2T |
| GET /api/chart/1 | 61 点干净序列 + MA；outliers_excluded=6 |
| GET /api/chart/1/forecast | ema 14 天预测 |
| GET /api/analyze/1（离线） | error 明确提示离线不可用；仍返回 forecast |
| GET /、/product/1 | HTTP 200 |
| GET search platform=jd | 501 + 合规说明 |
| 脏价过滤 | 1 / 0.01 / 9.9 / 过低 / 过高 / 999999 均拒绝 |

## 核心模块

- `app/main.py` — FastAPI + 页面
- `app/models.py` / `db.py` — SQLite 模型
- `app/collectors/` — mock / manual_csv / http_json / jd·taobao·pdd stub
- `app/cleaning/filters.py` — 异常价规则
- `app/forecast/models.py` — SMA/EMA/线性
- `app/llm/deepseek.py` — DeepSeek + 离线探测
- `app/api/` — REST
- `app/templates/` — ECharts 股市风格走势

## 合规摘要

不实现反爬绕过；真实电商为 stub；推荐开放平台 / 商家导出 CSV / 用户自建 http_json。

## 已知限制

见 ARCHITECTURE.md §10。Mock 非真实行情；真对接需官方 API。
