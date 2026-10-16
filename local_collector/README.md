# 本机已登录采集端（local_collector）

在**你自己的电脑**上，用你**已经手动登录**过的 Chrome / Edge（或 Playwright 持久化目录）打开关注商品页，解析售价，再 `POST` 到本服务的 `/api/ingest/prices`。

## 合规边界

- 采集只在用户本机、用户自己的登录会话下进行。
- **不**绕过验证码 / 风控；出现挑战页即停止并提示人工。
- **不**盗用他人 Cookie；**不**实现自动登录。
- 仅采 `config.json` 里配置的 URL / SKU，不做全站爬取。

## 5 步上手

1. **服务端**：在项目根 `.env` 设置 `INGEST_TOKEN=你的随机串`，启动 `uvicorn app.main:app --host 127.0.0.1 --port 8000`。
2. **本机依赖**：`cd local_collector && pip install -r requirements-local.txt && playwright install chromium`（若用系统 Chrome/Edge 可装对应浏览器）。
3. **配置**：复制 `config.example.json` → `config.json`，填写 `token`（与 `INGEST_TOKEN` 一致）、`service_url`、`user_data_dir`、关注商品的 `url` / `external_id` / `price_selectors`。
4. **先手动登录一次**：用同一浏览器 profile 打开京东/淘宝等，完成登录；**完全退出**浏览器后再跑脚本（系统用户目录被占用会启动失败）。
5. **采一次**：`python collect_once.py -c config.json`；成功后大盘关注列表会出现新价。定时可用系统 cron / 任务计划程序。

更细的中文步骤见 [../docs/LOCAL_COLLECTOR.md](../docs/LOCAL_COLLECTOR.md)。

## 用户数据目录（示例）

| 系统 | Chrome | Edge |
|------|--------|------|
| Linux | `~/.config/google-chrome` | `~/.config/microsoft-edge` |
| macOS | `~/Library/Application Support/Google/Chrome` | `~/Library/Application Support/Microsoft Edge` |
| Windows | `%LOCALAPPDATA%\Google\Chrome\User Data` | `%LOCALAPPDATA%\Microsoft\Edge\User Data` |

也可不用系统目录，改用独立 Playwright 持久化目录（例如 `./pw-profile`）：首次用 `headless: false` 跑起来后，在弹出窗口里**手动登录**，之后复用该目录即可。

## 价格选择器

各站点 DOM 常变。在 `products[].price_selectors` 里按优先级配置 CSS 选择器；解析失败会**明确报错**，请用浏览器开发者工具更新选择器，不要指望脚本自动「破解」页面。

## dry-run

```bash
python collect_once.py -c config.json --dry-run
```

只打印解析到的 JSON，不推送。
