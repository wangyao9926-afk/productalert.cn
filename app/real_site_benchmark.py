from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


ReferenceState = Literal["public_catalog_count", "sitemap_candidates", "manual_required", "negative_control"]


@dataclass(frozen=True)
class RealSiteReference:
    slug: str
    name: str
    url: str
    platform_hint: str
    reference_state: ReferenceState
    reference_count: int | None
    evidence: str
    is_control: bool = False


REAL_SITE_REFERENCES = (
    RealSiteReference("fanttik", "Fanttik", "https://fanttik.com/", "Shopify", "public_catalog_count", 212, "公开 products.json，2026-08-10 首页分页读取 212 条"),
    RealSiteReference("dji", "DJI 中国", "https://www.dji.com/cn", "Sitemap", "sitemap_candidates", 52, "公开 sitemap 中发现 52 条疑似商品 URL，尚未人工去重确认"),
    RealSiteReference("jisulife", "Jisulife", "https://jisulife.com/", "Shopify", "public_catalog_count", 25, "公开 products.json，2026-08-10 首页分页读取 25 条"),
    RealSiteReference("outdoormaster", "OutdoorMaster", "https://outdoormaster.com/", "Shopify", "public_catalog_count", 189, "公开 products.json，2026-08-10 首页分页读取 189 条"),
    RealSiteReference("romo", "ROMO", "https://www.romo.tech/", "Sitemap / custom", "manual_required", None, "公开 sitemap 可访问，但无可确认的公开商品目录接口"),
    RealSiteReference("anker", "Anker", "https://www.anker.com/", "Sitemap / multi-region", "manual_required", None, "多地区 sitemap 混合，候选 URL 不能直接代表一个地区的商品总数"),
    RealSiteReference("laifen", "Laifen", "https://www.laifen.net/", "Custom storefront", "manual_required", None, "公开 sitemap 可访问；常见目录端点返回 HTML 回退页，需人工确认入口"),
    RealSiteReference("zanearts", "Zane Arts", "https://zanearts.com/", "Shopify", "public_catalog_count", 139, "公开 products.json，2026-08-10 首页分页读取 139 条"),
    RealSiteReference("princetontec", "Princeton Tec", "https://princetontec.com/activity/camping/", "WooCommerce", "public_catalog_count", 76, "公开 WooCommerce Store API 的 X-WP-Total=76"),
    RealSiteReference("insta360", "Insta360", "https://www.insta360.com/", "Sitemap / custom", "sitemap_candidates", 323, "公开 sitemap 中发现 323 条疑似商品 URL，尚未人工去重确认"),
    RealSiteReference("hototools", "HOTO Tools 活动页", "https://hototools.com/pages/back-to-school", "Shopify", "negative_control", 54, "公开 products.json 有 54 条商品；提供的 URL 为活动页，用于验证不会误判目录", is_control=True),
)


def real_site_benchmark_summary() -> dict:
    sites = [asdict(site) for site in REAL_SITE_REFERENCES]
    core_sites = [site for site in REAL_SITE_REFERENCES if not site.is_control]
    public_catalog_sites = [site for site in core_sites if site.reference_state == "public_catalog_count"]
    return {
        "updated_at": "2026-08-10",
        "core_site_count": len(core_sites),
        "control_site_count": len(REAL_SITE_REFERENCES) - len(core_sites),
        "public_catalog_reference_count": len(public_catalog_sites),
        "accuracy_claim_allowed": False,
        "next_action": "完成每个核心站点的商品总数、抽样价格、库存和变体人工确认后，才能计算并对外使用真实准确率。",
        "sites": sites,
    }
