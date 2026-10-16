"""京东 / 淘宝 / 拼多多 stub：不实现反爬绕过，仅占位 + 合规指引。"""
from __future__ import annotations

from app.collectors.base import CollectorAdapter, PriceSnapshot, SearchResult
from app.collectors.registry import register_adapter


class _PlatformStub(CollectorAdapter):
    is_stub = True

    async def search(self, query: str, category: str | None = None, limit: int = 20) -> list[SearchResult]:
        raise NotImplementedError(self._todo())

    async def get_price(self, external_id: str) -> PriceSnapshot | None:
        raise NotImplementedError(self._todo())

    def _todo(self) -> str:
        return (
            f"[{self.code}] 未实现真实采集。"
            "推荐合规路径：① 开放平台/联盟 API；② 商家后台导出 CSV 后用 manual_csv；"
            "③ 用户本机浏览器扩展（已登录会话、仅自用）写入本地 API；"
            "④ 配置 http_json 指向自有合规数据服务。"
            "禁止：绕过验证码/风控、盗用 Cookie、大规模未授权抓取。"
        )


class JdStub(_PlatformStub):
    code = "jd"
    display_name = "京东（stub）"

    def compliance_note(self) -> str:
        return (
            "京东：申请京东开放平台/联盟推广 API；或商家后台导出；"
            "勿编写绕过登录与风控的爬虫。详见 README 合规说明。"
        )


class TaobaoStub(_PlatformStub):
    code = "taobao"
    display_name = "淘宝/天猫（stub）"

    def compliance_note(self) -> str:
        return (
            "淘宝：淘宝开放平台 / 阿里妈妈；商家后台导出；"
            "用户自用浏览器插件仅采集本账号可见页面。禁止攻击型爬虫。"
        )


class PddStub(_PlatformStub):
    code = "pdd"
    display_name = "拼多多（stub）"

    def compliance_note(self) -> str:
        return (
            "拼多多：多多进宝/开放平台；店铺后台导出；"
            "同样禁止绕过风控的未授权采集。"
        )


register_adapter(JdStub())
register_adapter(TaobaoStub())
register_adapter(PddStub())
