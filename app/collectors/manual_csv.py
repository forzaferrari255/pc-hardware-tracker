"""用户手动导入 CSV 价格。列：external_id,price[,collected_at,name,category,brand,model,url]"""
from __future__ import annotations

import csv
from datetime import datetime
from io import StringIO
from pathlib import Path

from app.collectors.base import CollectorAdapter, PriceSnapshot, SearchResult
from app.collectors.registry import register_adapter


class ManualCsvAdapter(CollectorAdapter):
    code = "manual_csv"
    display_name = "手动 CSV 导入"
    is_stub = False

    def __init__(self) -> None:
        self._rows: dict[str, dict] = {}

    def load_file(self, path: str | Path) -> int:
        text = Path(path).read_text(encoding="utf-8")
        return self.load_text(text)

    def load_text(self, text: str) -> int:
        reader = csv.DictReader(StringIO(text))
        n = 0
        for row in reader:
            eid = (row.get("external_id") or "").strip()
            if not eid or "price" not in row:
                continue
            self._rows[eid] = row
            n += 1
        return n

    async def search(self, query: str, category: str | None = None, limit: int = 20) -> list[SearchResult]:
        q = query.lower()
        out: list[SearchResult] = []
        for eid, row in self._rows.items():
            name = row.get("name") or eid
            cat = row.get("category")
            if category and cat and cat != category:
                continue
            if q and q not in name.lower() and q not in eid.lower():
                continue
            try:
                price = float(row["price"])
            except (TypeError, ValueError):
                price = None
            out.append(
                SearchResult(
                    external_id=eid,
                    name=name,
                    price=price,
                    url=row.get("url"),
                    brand=row.get("brand"),
                    model=row.get("model"),
                    category=cat,
                )
            )
            if len(out) >= limit:
                break
        return out

    async def get_price(self, external_id: str) -> PriceSnapshot | None:
        row = self._rows.get(external_id)
        if not row:
            return None
        try:
            price = float(row["price"])
        except (TypeError, ValueError):
            return None
        ts = row.get("collected_at")
        collected = None
        if ts:
            try:
                collected = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                collected = None
        return PriceSnapshot(
            external_id=external_id,
            price=price,
            collected_at=collected,
            title=row.get("name"),
            raw=dict(row),
        )

    def compliance_note(self) -> str:
        return "用户自有数据导入，请确保来源合法（例如商家后台导出）。"


_manual = ManualCsvAdapter()
register_adapter(_manual)
