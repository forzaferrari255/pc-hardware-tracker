#!/usr/bin/env python3
"""
本机已登录会话采价 → POST 到本服务 /api/ingest/prices。

合规说明：
- 仅在用户自己的电脑、用户已手动登录过的浏览器 profile 下运行。
- 不绕过验证码 / 风控；检测到挑战页即停止并提示人工处理。
- 不盗用他人 Cookie；不实现自动登录。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError:
    print("请先安装依赖: pip install -r requirements-local.txt", file=sys.stderr)
    sys.exit(1)

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
except ImportError:
    print("请先安装 Playwright: pip install playwright && playwright install chromium", file=sys.stderr)
    sys.exit(1)


DEFAULT_SELECTORS = [
    "meta[itemprop='price']",
    "[itemprop='price']",
    ".price",
    "[class*='price']",
]


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"配置文件不存在: {path}\n请复制 config.example.json 为 config.json 并填写。")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not data.get("service_url"):
        raise SystemExit("config.service_url 必填")
    if not data.get("token") or data["token"] == "change-me-to-match-INGEST_TOKEN":
        raise SystemExit("请将 config.token 改成与服务端 INGEST_TOKEN 一致的值")
    if not data.get("products"):
        raise SystemExit("config.products 不能为空")
    return data


def default_user_data_dir(channel: str) -> Path:
    """给出常见 Chrome/Edge 用户数据目录提示路径（不自动偷用，需用户确认）。"""
    home = Path.home()
    # Linux / macOS / Windows 常见路径（本脚本主要在 Linux/mac 上文档化）
    candidates = {
        "chrome": [
            home / ".config" / "google-chrome",
            home / "Library" / "Application Support" / "Google" / "Chrome",
            home / "AppData" / "Local" / "Google" / "Chrome" / "User Data",
        ],
        "msedge": [
            home / ".config" / "microsoft-edge",
            home / "Library" / "Application Support" / "Microsoft Edge",
            home / "AppData" / "Local" / "Microsoft" / "Edge" / "User Data",
        ],
    }
    for p in candidates.get(channel, candidates["chrome"]):
        if p.exists():
            return p
    return candidates.get(channel, candidates["chrome"])[0]


def page_looks_like_challenge(text: str, keywords: list[str]) -> str | None:
    lower = text.lower()
    for kw in keywords:
        if kw.lower() in lower or kw in text:
            return kw
    return None


def parse_price_from_text(text: str) -> float | None:
    """从一段文本里抽出第一个合理价格数字。"""
    if not text:
        return None
    text = text.replace(",", "").replace("，", "").replace("¥", "").replace("￥", "")
    m = re.search(r"(\d+(?:\.\d{1,2})?)", text)
    if not m:
        return None
    try:
        val = float(m.group(1))
    except ValueError:
        return None
    if val <= 0 or val > 1_000_000:
        return None
    return val


def extract_price(page, selectors: list[str]) -> float | None:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() == 0:
                continue
            # meta content
            tag = loc.evaluate("el => el.tagName.toLowerCase()")
            if tag == "meta":
                content = loc.get_attribute("content")
                price = parse_price_from_text(content or "")
                if price is not None:
                    return price
            text = loc.inner_text(timeout=2000)
            price = parse_price_from_text(text)
            if price is not None:
                return price
            # content / data attributes
            for attr in ("content", "data-price", "price"):
                v = loc.get_attribute(attr)
                price = parse_price_from_text(v or "")
                if price is not None:
                    return price
        except Exception:
            continue
    # 兜底：页面标题附近不盲目全页扫大额，避免误采；明确失败
    return None


def collect_one(page, product: dict, cfg: dict) -> dict[str, Any]:
    url = product.get("url")
    if not url:
        raise RuntimeError(f"商品 {product.get('external_id')} 缺少 url")

    page.goto(url, wait_until="domcontentloaded", timeout=cfg.get("timeout_ms", 45000))
    page.wait_for_timeout(800)

    body_text = ""
    try:
        body_text = page.inner_text("body", timeout=5000)
    except Exception:
        body_text = page.content()[:8000]

    hit = page_looks_like_challenge(body_text, cfg.get("challenge_keywords") or [])
    if hit and cfg.get("stop_on_challenge", True):
        raise RuntimeError(
            f"检测到疑似验证码/风控页面（关键词: {hit}）。"
            f"请在本机浏览器中手动完成验证后重试；本采集端不会自动绕过。"
        )

    selectors = product.get("price_selectors") or DEFAULT_SELECTORS
    price = extract_price(page, selectors)
    if price is None:
        raise RuntimeError(
            f"无法从页面解析价格: {url}\n"
            f"请在 config.json 中为该商品配置可用的 price_selectors，"
            f"或确认已登录且页面正常展示售价。"
        )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "external_id": product["external_id"],
        "price": price,
        "name": product.get("name"),
        "category": product.get("category") or "other",
        "brand": product.get("brand"),
        "model": product.get("model"),
        "url": url,
        "platform": product.get("platform") or "local_browser",
        "collected_at": now,
        "source": "local_collector",
    }


def push_prices(service_url: str, token: str, items: list[dict]) -> dict:
    url = service_url.rstrip("/") + "/api/ingest/prices"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=30.0) as client:
        r = client.post(url, headers=headers, json=items)
        if r.status_code >= 400:
            raise RuntimeError(f"ingest 失败 HTTP {r.status_code}: {r.text[:500]}")
        return r.json()


def run(config_path: Path, dry_run: bool = False) -> int:
    cfg = load_config(config_path)
    channel = (cfg.get("channel") or "chrome").lower()
    user_data = cfg.get("user_data_dir") or ""
    if not user_data:
        guessed = default_user_data_dir(channel)
        print(
            f"未配置 user_data_dir。常见路径示例: {guessed}\n"
            f"请在 config.json 中填写「你已手动登录电商网站」的浏览器用户数据目录，\n"
            f"或改用 Playwright persistent 目录（见 README）。\n"
            f"注意：使用系统 Chrome 用户目录时，请先完全退出 Chrome 再运行本脚本。",
            file=sys.stderr,
        )
        return 2

    user_data_path = Path(user_data).expanduser()
    user_data_path.mkdir(parents=True, exist_ok=True)

    collected: list[dict] = []
    errors: list[str] = []

    with sync_playwright() as p:
        browser_type = p.chromium
        launch_kwargs: dict[str, Any] = {
            "user_data_dir": str(user_data_path),
            "headless": bool(cfg.get("headless", False)),
            "viewport": {"width": 1280, "height": 900},
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        # channel: chrome / msedge — 使用本机已安装浏览器
        if channel in ("chrome", "msedge", "chromium"):
            if channel != "chromium":
                launch_kwargs["channel"] = channel

        try:
            context = browser_type.launch_persistent_context(**launch_kwargs)
        except Exception as e:
            print(
                f"无法启动浏览器 persistent context: {e}\n"
                f"排查：1) 浏览器是否已完全退出 2) user_data_dir 权限 3) playwright install chromium",
                file=sys.stderr,
            )
            return 3

        page = context.new_page()
        pause = int(cfg.get("pause_between_ms") or 2000)

        for product in cfg["products"]:
            eid = product.get("external_id", "?")
            try:
                item = collect_one(page, product, cfg)
                collected.append(item)
                print(f"[OK] {eid} -> {item['price']}")
            except Exception as e:
                msg = f"[FAIL] {eid}: {e}"
                print(msg, file=sys.stderr)
                errors.append(msg)
                # 风控则整批停止
                if "验证码" in str(e) or "风控" in str(e) or "captcha" in str(e).lower():
                    print("因验证码/风控停止后续采集。", file=sys.stderr)
                    break
            page.wait_for_timeout(pause)

        context.close()

    if not collected:
        print("没有成功采集到任何价格。", file=sys.stderr)
        return 1

    if dry_run:
        print(json.dumps(collected, ensure_ascii=False, indent=2))
        print("dry-run：未推送到服务端")
        return 0 if not errors else 1

    resp = push_prices(cfg["service_url"], cfg["token"], collected)
    print(json.dumps(resp, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


def main() -> None:
    ap = argparse.ArgumentParser(description="本机已登录采价并推送到 PC Hardware Tracker")
    ap.add_argument(
        "-c",
        "--config",
        default=str(Path(__file__).resolve().parent / "config.json"),
        help="配置文件路径（默认 local_collector/config.json）",
    )
    ap.add_argument("--dry-run", action="store_true", help="只解析价格，不 POST")
    args = ap.parse_args()
    raise SystemExit(run(Path(args.config), dry_run=args.dry_run))


if __name__ == "__main__":
    main()
