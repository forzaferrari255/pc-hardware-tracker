"""不合理价格过滤：绝对阈值、缺货占位、中位数偏离、Z-score。"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median, pstdev

from app.config import get_settings


@dataclass
class FilterResult:
    accepted: bool
    reason: str | None = None
    is_outlier: bool = False


class PriceFilter:
    """可配置规则；对单点判决时可传入同商品历史价列表。"""

    PLACEHOLDER_PRICES = {0.0, 0.01, 0.1, 1.0, 9.9, 9.99, 99.0, 999999.0, 9999999.0}

    def __init__(
        self,
        min_price: float | None = None,
        max_price: float | None = None,
        median_deviation_ratio: float | None = None,
        zscore_threshold: float | None = None,
        relative_window: int = 30,
    ) -> None:
        s = get_settings()
        self.min_price = min_price if min_price is not None else s.filter_min_price
        self.max_price = max_price if max_price is not None else s.filter_max_price
        self.median_deviation_ratio = (
            median_deviation_ratio
            if median_deviation_ratio is not None
            else s.filter_median_deviation_ratio
        )
        self.zscore_threshold = (
            zscore_threshold if zscore_threshold is not None else s.filter_zscore_threshold
        )
        self.relative_window = relative_window

    def check(self, price: float, history: list[float] | None = None) -> FilterResult:
        if price is None or not isinstance(price, (int, float)):
            return FilterResult(False, "非数值价格", True)
        price = float(price)

        if price in self.PLACEHOLDER_PRICES or price <= 0:
            return FilterResult(False, f"占位/无效价 {price}", True)

        if price < self.min_price:
            return FilterResult(False, f"低于最低阈值 {self.min_price}", True)

        if price > self.max_price:
            return FilterResult(False, f"高于最高阈值 {self.max_price}", True)

        hist = [float(x) for x in (history or []) if x is not None and float(x) > 0]
        # 只用近期窗口，避免长期缓升/缓降被 Z-score 误杀
        clean_hist = hist[-self.relative_window :] if hist else []

        if len(clean_hist) >= 5:
            med = median(clean_hist)
            if med > 0:
                deviation = abs(price - med) / med
                if deviation > self.median_deviation_ratio:
                    return FilterResult(
                        False,
                        f"相对中位数偏离过大 ({deviation:.0%} > {self.median_deviation_ratio:.0%}, med={med:.2f})",
                        True,
                    )

        if len(clean_hist) >= 8:
            mu = sum(clean_hist) / len(clean_hist)
            sd = pstdev(clean_hist)
            if sd > 1e-6:
                z = abs(price - mu) / sd
                if z > self.zscore_threshold:
                    return FilterResult(
                        False,
                        f"Z-score 离群 (z={z:.2f} > {self.zscore_threshold})",
                        True,
                    )

        if len(clean_hist) >= 5:
            med = median(clean_hist)
            if med > 0 and price < med * 0.15 and price < 100:
                return FilterResult(False, "疑似虚假促销/券后假价", True)

        return FilterResult(True, None, False)

    def filter_series(self, prices: list[float]) -> list[tuple[float, FilterResult]]:
        accepted: list[float] = []
        out: list[tuple[float, FilterResult]] = []
        for p in prices:
            r = self.check(p, accepted)
            out.append((p, r))
            if r.accepted:
                accepted.append(p)
        return out
