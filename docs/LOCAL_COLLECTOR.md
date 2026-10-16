# 本机已登录采集 → 自动推送到本服务（一步步）

目标：每天（或每小时）自动拿到关注硬件的当日价，**不用手填 CSV**。采集发生在你自己的电脑、你自己的登录态下；服务端只负责鉴权入库。

## 架构

```
[你的电脑]
  Chrome/Edge 已登录会话
       │ Playwright 打开 config 里的商品 URL
       │ 解析售价（可配置选择器）
       ▼
  collect_once.py ──POST Bearer token──► 本服务 POST /api/ingest/prices
                                              │
                                              ▼
                                         SQLite PricePoint
                                         （outlier 过滤 + 可选自动关注）
```

## 一、服务端准备

1. 复制 `.env.example` 为 `.env`（若还没有）。
2. 设置随机 token，例如：

```bash
# .env
INGEST_TOKEN=请换成足够长的随机字符串
INGEST_AUTO_WATCH=1
```

3. 启动服务：

```bash
cd /path/to/pc-hardware-tracker
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

4. 用 curl 验证 ingest（**不要**真去爬电商站；这里只测入库）：

```bash
curl -sS -X POST 'http://127.0.0.1:8000/api/ingest/prices' \
  -H 'Authorization: Bearer 请换成足够长的随机字符串' \
  -H 'Content-Type: application/json' \
  -d '[{
    "external_id": "demo-gpu-5080",
    "price": 8299,
    "name": "NVIDIA RTX 5080 16G",
    "category": "gpu",
    "brand": "NVIDIA",
    "model": "RTX 5080",
    "platform": "local_browser",
    "source": "curl-test"
  }]'
```

也可用 Header `X-Ingest-Token: <token>` 代替 `Authorization`。

成功时返回 `ok: true` 以及 `product_id`；打开 http://127.0.0.1:8000/ 应能在关注列表看到该商品。

## 二、本机采集端

1. 安装依赖：

```bash
cd local_collector
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-local.txt
playwright install chromium
```

2. 复制配置：

```bash
cp config.example.json config.json
```

编辑要点：

| 字段 | 说明 |
|------|------|
| `service_url` | 本服务地址，如 `http://127.0.0.1:8000` |
| `token` | 与 `.env` 的 `INGEST_TOKEN` 完全一致 |
| `user_data_dir` | 已登录的浏览器用户目录，或空目录作 Playwright 持久化 profile |
| `channel` | `chrome` / `msedge` / `chromium` |
| `headless` | 首次登录建议 `false`；稳定后可 `true` |
| `products` | 关注列表：`external_id`、`url`、可选 `price_selectors` |
| `stop_on_challenge` | 默认 `true`：遇到验证码关键词即停 |

3. **手动登录一次**

- **方式 A（系统 Chrome/Edge 目录）**：平时用的浏览器先登录好电商账号 → **完全退出**浏览器 → 把用户数据目录填进 `user_data_dir` → 再跑脚本。  
- **方式 B（推荐独立 profile）**：`user_data_dir` 设为例如 `./pw-profile`，`headless: false`，第一次运行时在弹出窗口里手动登录各站点，之后复用该目录。

4. 采一次：

```bash
python collect_once.py -c config.json
# 或先 dry-run
python collect_once.py -c config.json --dry-run
```

5. 定时（示例 cron，每小时）：

```cron
0 * * * * cd /path/to/pc-hardware-tracker/local_collector && .venv/bin/python collect_once.py -c config.json >> collect.log 2>&1
```

Windows 可用「任务计划程序」调用同一命令。

## 三、验证码 / 风控

脚本检测到页面含「验证码」「安全验证」「captcha」等关键词时会**立即停止**，并打印提示。请你：

1. 用同一 profile 手动打开该 URL，完成验证；
2. 确认能正常看到售价；
3. 再重新运行 `collect_once.py`。

**本项目不会、也不应实现自动过验证码。**

## 四、选择器失效怎么办

电商 DOM 经常改版。用浏览器开发者工具选中售价元素，把 CSS 选择器写进该商品的 `price_selectors` 数组（靠前优先）。解析失败时脚本会报错退出该商品，而不是瞎猜价格。

## 五、与 `http_json` / CSV 的关系

| 方式 | 谁采价 | 是否手填 |
|------|--------|----------|
| `local_collector` → `/api/ingest/prices` | 本机 Playwright | 否（自动） |
| `http_json` adapter | 你自建的中间服务 | 否 |
| `manual_csv` | 你导出文件 | 是（兜底） |

本机采集端走的是 **ingest API**（主动推），不是服务端定时去拉电商站。

## 六、安全提醒

- `INGEST_TOKEN` 与 `config.json` 含密钥，**不要提交到 Git**（根目录 `.gitignore` 已忽略 `.env`；请自行忽略 `local_collector/config.json`）。
- 服务建议只监听 `127.0.0.1`；若暴露到局域网/公网，必须使用强 token 并考虑 HTTPS。
