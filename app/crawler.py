from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from html import unescape
from typing import Any, Iterable, Sequence
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.rate_limit import record_domain_rate_limit, record_domain_success, wait_for_domain_slot
from app.render_worker import try_render_page
from app.url_safety import UnsafeUrlError, canonicalize_url, resolve_redirect_url, validate_public_http_url


PRODUCT_HINTS = (
    "product",
    "products",
    "new",
    "news",
    "launch",
    "release",
    "collection",
    "collections",
    "shop",
    "store",
    "item",
    "goods",
    "新品",
    "上新",
    "产品",
)

FEATURE_HINTS = (
    "feature",
    "benefit",
    "spec",
    "highlight",
    "designed",
    "supports",
    "includes",
    "功能",
    "卖点",
    "特点",
    "规格",
    "亮点",
    "支持",
    "采用",
    "适合",
)


@dataclass
class ProductCandidate:
    url: str
    title_hint: str | None = None
    payload: dict[str, Any] | None = None
    discovery_sources: tuple[str, ...] = ()


@dataclass
class CatalogDiscoveryResult:
    candidates: list[ProductCandidate]
    reference_count: int | None
    discovery_source_counts: dict[str, int]
    adapter_attempts: list[dict[str, Any]]


@dataclass
class ExtractedVariant:
    external_id: str
    sku: str | None
    title: str | None
    option_values: list[str]
    price: str | None
    price_amount: float | None
    compare_at_price: float | None
    availability: str | None


@dataclass
class ExtractedIdentifier:
    kind: str
    value: str
    raw_value: str
    provenance: str


@dataclass
class ExtractedProduct:
    url: str
    title: str
    description: str
    image_url: str | None
    price: str | None
    price_amount: float | None
    currency: str | None
    compare_at_price: float | None
    availability: str | None
    variant_count: int | None
    variants: list[ExtractedVariant]
    features: list[str]
    extraction_source: str
    confidence_score: float
    field_confidence: dict[str, float]
    confidence_reasons: list[str]
    content_hash: str
    raw_text: str
    identifiers: list[ExtractedIdentifier] = field(default_factory=list)


@dataclass
class ExtractedSourceText:
    url: str
    selector: str | None
    text: str
    content_hash: str
    text_hash: str
    capture_method: str
    http_status: int | None
    content_type: str | None
    content_length: int


@dataclass
class FetchedDocument:
    url: str
    content: str
    status_code: int
    content_type: str | None


@dataclass(frozen=True)
class FetchResult:
    url: str
    status_code: int | None
    content: str | None
    error_category: str | None
    retry_after_seconds: int | None


class ProductFetchError(RuntimeError):
    def __init__(self, error_category: str, http_status: int | None = None, *, retry_after_seconds: int | None = None) -> None:
        super().__init__(error_category)
        self.error_category = error_category
        self.http_status = http_status
        self.retry_after_seconds = retry_after_seconds


def fetch_result_from_response(
    url: str,
    *,
    status_code: int,
    headers: dict[str, str],
    content: str,
) -> FetchResult:
    if status_code == 429:
        retry_after = headers.get("Retry-After", "").strip()
        return FetchResult(
            url=url,
            status_code=status_code,
            content=None,
            error_category="rate_limited",
            retry_after_seconds=int(retry_after) if retry_after.isdigit() else None,
        )
    if status_code == 403:
        return FetchResult(url, status_code, None, "blocked", None)
    if status_code >= 400:
        return FetchResult(url, status_code, None, "http_error", None)
    return FetchResult(url, status_code, content, None, None)


def raise_for_fetch_failure(result: FetchResult) -> None:
    if result.error_category:
        raise ProductFetchError(
            result.error_category,
            result.status_code,
            retry_after_seconds=result.retry_after_seconds,
        )


def classify_product_url(url: str) -> tuple[str, str]:
    path = urlparse(url).path.lower().strip("/")
    segments = [segment for segment in path.split("/") if segment]
    joined = "/" + path

    promo_markers = (
        "sale",
        "deals",
        "outlet",
        "refurbished",
        "certified-refurbished",
        "campaign",
        "promo",
        "promotion",
        "scene-picks",
        "landing",
        "collections/all",
    )
    collection_markers = (
        "collections",
        "collection",
        "category",
        "categories",
        "catalog",
    )
    utility_markers = (
        "compare",
        "comparison",
        "compare-products",
        "search",
        "cart",
        "account",
    )
    product_markers = ("products", "product")

    if any(segment in collection_markers for segment in segments):
        return "collection_page", "false_positive"
    if segments and segments[-1] in utility_markers:
        return "utility_page", "false_positive"
    if any(segment in product_markers for segment in segments) and len(segments) >= 2:
        return "product_detail", "confirmed"
    if any(marker in joined for marker in promo_markers):
        return "promo_page", "false_positive"
    return "unknown", "unreviewed"


def normalize_url(url: str) -> str:
    return canonicalize_url(url)


def same_domain(a: str, b: str) -> bool:
    return urlparse(a).netloc.lower().removeprefix("www.") == urlparse(b).netloc.lower().removeprefix("www.")


def looks_relevant(url: str, text: str = "") -> bool:
    haystack = f"{url} {text}".lower()
    return any(hint.lower() in haystack for hint in PRODUCT_HINTS)


def matches_keyword_rules(
    candidate: ProductCandidate,
    include_keywords: Sequence[str],
    exclude_keywords: Sequence[str],
    require_relevance: bool,
) -> bool:
    haystack = f"{candidate.url} {candidate.title_hint or ''}".lower()
    if exclude_keywords and any(keyword.lower() in haystack for keyword in exclude_keywords):
        return False
    if include_keywords:
        return any(keyword.lower() in haystack for keyword in include_keywords)
    if require_relevance:
        return looks_relevant(candidate.url, candidate.title_hint or "")
    return True


async def fetch_document(client: httpx.AsyncClient, url: str) -> FetchedDocument | None:
    safe_url = validate_public_http_url(url)
    try:
        for _ in range(5):
            await wait_for_domain_slot(safe_url)
            res = await client.get(safe_url, follow_redirects=False)
            if res.status_code in {301, 302, 303, 307, 308}:
                safe_url = resolve_redirect_url(safe_url, res.headers.get("location", ""))
                continue
            break
        else:
            return None
        if res.status_code >= 400:
            return None
        content_type = res.headers.get("content-type", "")
        if content_type and not any(kind in content_type for kind in ("text", "xml", "html")):
            return None
        return FetchedDocument(
            url=safe_url,
            content=res.text,
            status_code=res.status_code,
            content_type=content_type or None,
        )
    except (httpx.HTTPError, UnsafeUrlError):
        return None


async def fetch_product_result(client: httpx.AsyncClient, url: str) -> FetchResult:
    safe_url = validate_public_http_url(url)
    try:
        for _ in range(5):
            await wait_for_domain_slot(safe_url)
            response = await client.get(safe_url, follow_redirects=False)
            if response.status_code in {301, 302, 303, 307, 308}:
                safe_url = resolve_redirect_url(safe_url, response.headers.get("location", ""))
                continue
            result = fetch_result_from_response(
                safe_url,
                status_code=response.status_code,
                headers=dict(response.headers),
                content=response.text,
            )
            if result.error_category == "rate_limited":
                record_domain_rate_limit(safe_url, result.retry_after_seconds)
            if result.error_category:
                return result
            record_domain_success(safe_url)
            content_type = response.headers.get("content-type", "")
            if content_type and not any(kind in content_type for kind in ("text", "html")):
                return FetchResult(safe_url, response.status_code, None, "unsupported_content", None)
            return result
        return FetchResult(safe_url, None, None, "redirect_loop", None)
    except httpx.TimeoutException:
        return FetchResult(safe_url, None, None, "timeout", None)
    except (httpx.HTTPError, UnsafeUrlError):
        return FetchResult(safe_url, None, None, "fetch_failed", None)


async def fetch_text(client: httpx.AsyncClient, url: str) -> str | None:
    document = await fetch_document(client, url)
    return document.content if document else None


def canonical_candidate_key(candidate: ProductCandidate) -> str:
    parsed = urlparse(candidate.url)
    item_type, _ = classify_product_url(candidate.url)
    if item_type == "product_detail":
        segments = [segment for segment in parsed.path.strip("/").split("/") if segment]
        product_segment = next((segment for segment in ("products", "product") if segment in segments), None)
        if product_segment:
            index = segments.index(product_segment)
            if index + 1 < len(segments):
                return f"{parsed.netloc.lower().removeprefix('www.')}/{product_segment}/{segments[index + 1].lower()}"
    return normalize_url(candidate.url)


def merge_catalog_candidates(candidates: Iterable[ProductCandidate], limit: int) -> list[ProductCandidate]:
    seen: dict[str, int] = {}
    unique: list[ProductCandidate] = []
    for candidate in candidates:
        clean = candidate.url.split("#", 1)[0].rstrip("/")
        normalized_candidate = ProductCandidate(clean, candidate.title_hint, candidate.payload, candidate.discovery_sources)
        key = canonical_candidate_key(normalized_candidate)
        if key in seen:
            index = seen[key]
            existing = unique[index]
            payload = existing.payload or candidate.payload
            title_hint = existing.title_hint or candidate.title_hint
            sources = tuple(dict.fromkeys((*existing.discovery_sources, *candidate.discovery_sources)))
            unique[index] = ProductCandidate(existing.url, title_hint, payload, sources)
            continue
        seen[key] = len(unique)
        unique.append(normalized_candidate)
        if len(unique) >= limit:
            break
    return unique


def unique_urls(candidates: Iterable[ProductCandidate], limit: int) -> list[ProductCandidate]:
    return merge_catalog_candidates(candidates, limit)


def xml_candidates(xml_text: str, base_url: str) -> list[ProductCandidate]:
    soup = BeautifulSoup(xml_text, "xml")
    candidates: list[ProductCandidate] = []

    for loc in soup.find_all("loc"):
        url = (loc.get_text() or "").strip()
        if url:
            candidates.append(ProductCandidate(url))

    for item in soup.find_all("item"):
        link = item.find("link")
        title = item.find("title")
        url = (link.get_text() if link else "").strip()
        if url:
            candidates.append(ProductCandidate(urljoin(base_url, url), title.get_text(strip=True) if title else None))

    for link in soup.find_all("link"):
        href = link.get("href")
        if href:
            candidates.append(ProductCandidate(urljoin(base_url, href)))

    return candidates


def woocommerce_product_candidates_from_payload(payload: Any, source_url: str) -> list[ProductCandidate]:
    if not isinstance(payload, list):
        return []
    candidates: list[ProductCandidate] = []
    for product in payload:
        if not isinstance(product, dict):
            continue
        permalink = product.get("permalink")
        if not isinstance(permalink, str) or not permalink.strip():
            continue
        url = urljoin(source_url, permalink)
        if not same_domain(source_url, url):
            continue
        candidates.append(
            ProductCandidate(
                url,
                clean_text(str(product.get("name") or "")) or None,
                {"kind": "woocommerce_product", "product": product},
                ("woocommerce_store_api",),
            )
        )
    return candidates


def jsonld_item_list_candidates(html: str, base_url: str) -> list[ProductCandidate]:
    soup = BeautifulSoup(html, "lxml")
    candidates: list[ProductCandidate] = []
    for script in soup.find_all("script", type=lambda value: value and "ld+json" in value):
        try:
            data = json.loads(script.string or script.get_text() or "")
        except json.JSONDecodeError:
            continue
        for item_list in flatten_jsonld(data):
            if not jsonld_type_matches(item_list, "itemlist"):
                continue
            elements = item_list.get("itemListElement")
            if not isinstance(elements, list):
                continue
            for element in elements:
                value = element.get("item", element) if isinstance(element, dict) else element
                if isinstance(value, str):
                    url, title = value, None
                elif isinstance(value, dict):
                    url = value.get("url") or value.get("@id")
                    title = value.get("name")
                else:
                    continue
                if not isinstance(url, str) or not url.strip():
                    continue
                candidate_url = urljoin(base_url, url)
                if not same_domain(base_url, candidate_url):
                    continue
                candidates.append(
                    ProductCandidate(
                        candidate_url,
                        clean_text(str(title or "")) or None,
                        {"kind": "jsonld_product"} if isinstance(value, dict) and jsonld_type_matches(value, "product") else None,
                        ("json_ld_item_list",),
                    )
                )
    return candidates


def discover_product_candidates(
    source_url: str,
    *,
    sitemap_documents: dict[str, str],
    limit: int = 1000,
) -> list[ProductCandidate]:
    candidates: list[ProductCandidate] = []
    for sitemap_url, sitemap_text in sitemap_documents.items():
        candidates.extend(xml_candidates(sitemap_text, sitemap_url or source_url))
    product_candidates = [
        ProductCandidate(normalize_url(candidate.url), candidate.title_hint, candidate.payload)
        for candidate in candidates
        if same_domain(source_url, candidate.url)
        and classify_product_url(candidate.url)[0] == "product_detail"
    ]
    return unique_urls(sorted(product_candidates, key=candidate_priority), limit)


def looks_like_sitemap(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith(".xml") and "sitemap" in path


def sitemap_priority(candidate: ProductCandidate) -> tuple[int, int, str]:
    url = candidate.url.lower()
    locale_rank = locale_priority(candidate.url)
    if "sitemap_products" in url or "product" in url:
        return (0, locale_rank, url)
    if "sitemap_collections" in url or "collection" in url:
        return (1, locale_rank, url)
    return (2, locale_rank, url)


def locale_priority(url: str) -> int:
    segments = [segment for segment in urlparse(url).path.lower().split("/") if segment]
    if not segments:
        return 0
    first = segments[0]
    if first in {"products", "collections"}:
        return 0
    if first.startswith("en-") or first in {"en", "us", "global"}:
        return 1
    if re.match(r"^[a-z]{2}-[a-z]{2}$", first):
        return 3
    return 2


def candidate_priority(candidate: ProductCandidate) -> tuple[int, int, str]:
    item_type, _ = classify_product_url(candidate.url)
    locale_rank = locale_priority(candidate.url)
    if candidate.payload and candidate.payload.get("kind") == "shopify_product":
        return (0, -1, candidate.url)
    if item_type == "product_detail":
        return (0, locale_rank, candidate.url)
    if item_type == "collection_page":
        return (1, locale_rank, candidate.url)
    if looks_like_sitemap(candidate.url):
        return (3, locale_rank, candidate.url)
    return (2, locale_rank, candidate.url)


def html_candidates(html: str, base_url: str, selector: str | None = None) -> list[ProductCandidate]:
    soup = BeautifulSoup(html, "lxml")
    roots = [soup]
    if selector:
        try:
            selected = soup.select(selector)
            if selected:
                roots = selected
        except Exception:
            roots = [soup]
    candidates: list[ProductCandidate] = []
    for root in roots:
        for link in root.find_all("a", href=True):
            href = urljoin(base_url, link["href"])
            text = " ".join(link.get_text(" ", strip=True).split())
            if same_domain(base_url, href):
                candidates.append(ProductCandidate(href, text or None))
    return candidates


async def rendered_candidates(source_url: str, selector: str | None = None) -> list[ProductCandidate]:
    rendered = await try_render_page(source_url, selector=selector)
    if not rendered or not rendered.html:
        return []
    return html_candidates(rendered.html, rendered.url or source_url, selector)


def with_discovery_source(candidates: Iterable[ProductCandidate], source: str) -> list[ProductCandidate]:
    return [
        ProductCandidate(
            candidate.url,
            candidate.title_hint,
            candidate.payload,
            tuple(dict.fromkeys((*candidate.discovery_sources, source))),
        )
        for candidate in candidates
    ]


async def discover_sitemap_candidates(
    client: httpx.AsyncClient,
    source_url: str,
    sitemap_url: str,
    *,
    max_documents: int = 30,
    max_depth: int = 3,
) -> list[ProductCandidate]:
    """Fetch a bounded sitemap tree so nested catalog indexes are not skipped."""
    candidates: list[ProductCandidate] = []
    queued: list[tuple[str, int]] = [(sitemap_url, 0)]
    visited: set[str] = set()

    while queued and len(visited) < max_documents:
        current_url, depth = queued.pop(0)
        normalized_url = normalize_url(current_url)
        if normalized_url in visited or not same_domain(source_url, normalized_url):
            continue
        visited.add(normalized_url)

        sitemap_text = await fetch_text(client, normalized_url)
        if not sitemap_text:
            continue

        source = "product_sitemap" if "product" in urlparse(normalized_url).path.lower() else "sitemap"
        sitemap_candidates = with_discovery_source(xml_candidates(sitemap_text, normalized_url), source)
        candidates.extend(sitemap_candidates)

        if depth >= max_depth:
            continue
        child_sitemaps = [
            candidate
            for candidate in sitemap_candidates
            if same_domain(source_url, candidate.url) and looks_like_sitemap(candidate.url)
        ]
        queued.extend(
            (candidate.url, depth + 1)
            for candidate in sorted(child_sitemaps, key=sitemap_priority)
            if normalize_url(candidate.url) not in visited
        )

    return candidates


def collection_next_page_url(html: str, base_url: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    next_markers = ("next", "下一页", "下页", "下一頁", "›", "→")
    for anchor in soup.find_all("a", href=True):
        rel = " ".join(anchor.get("rel") or [])
        label = " ".join(
            value
            for value in (
                anchor.get_text(" ", strip=True),
                anchor.get("aria-label", ""),
                anchor.get("title", ""),
                rel,
            )
            if value
        ).lower()
        if not ("next" in rel.lower() or any(marker in label for marker in next_markers)):
            continue
        candidate_url = urljoin(base_url, anchor["href"])
        if same_domain(base_url, candidate_url) and classify_product_url(candidate_url)[0] == "collection_page":
            return candidate_url
    return None


async def discover_collection_candidates(
    client: httpx.AsyncClient,
    source_url: str,
    seed_candidates: Iterable[ProductCandidate],
    *,
    max_pages: int = 30,
) -> list[ProductCandidate]:
    """Discover product links from bounded collection-page pagination."""
    collection_urls = [
        candidate.url
        for candidate in sorted(seed_candidates, key=candidate_priority)
        if same_domain(source_url, candidate.url)
        and classify_product_url(candidate.url)[0] == "collection_page"
    ]
    queued = [(url, 0) for url in dict.fromkeys(collection_urls)]
    visited: set[str] = set()
    candidates: list[ProductCandidate] = []

    while queued and len(visited) < max_pages:
        current_url, page_number = queued.pop(0)
        normalized_url = normalize_url(current_url)
        if normalized_url in visited:
            continue
        visited.add(normalized_url)

        page = await fetch_text(client, normalized_url)
        if not page:
            continue
        candidates.extend(with_discovery_source(html_candidates(page, normalized_url), "collection_page"))

        next_page = collection_next_page_url(page, normalized_url)
        if next_page and page_number + 1 < max_pages and normalize_url(next_page) not in visited:
            queued.append((next_page, page_number + 1))

    return candidates


def candidate_is_confirmed_product(candidate: ProductCandidate) -> bool:
    kind = (candidate.payload or {}).get("kind")
    return kind in {"shopify_product", "woocommerce_product", "jsonld_product"} or classify_product_url(candidate.url)[0] == "product_detail"


def matches_catalog_candidate_rules(
    candidate: ProductCandidate,
    include_keywords: Sequence[str],
    exclude_keywords: Sequence[str],
    require_relevance: bool,
) -> bool:
    haystack = f"{candidate.url} {candidate.title_hint or ''}".lower()
    if exclude_keywords and any(keyword.lower() in haystack for keyword in exclude_keywords):
        return False
    if include_keywords:
        return any(keyword.lower() in haystack for keyword in include_keywords)
    return candidate_is_confirmed_product(candidate) or not require_relevance or looks_relevant(candidate.url, candidate.title_hint or "")


def discovery_source_counts(candidates: Iterable[ProductCandidate]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        for source in candidate.discovery_sources:
            counts[source] = counts.get(source, 0) + 1
    return counts


async def shopify_catalog_discovery(
    client: httpx.AsyncClient,
    source_url: str,
    max_pages: int = 20,
) -> tuple[list[ProductCandidate], int | None, dict[str, Any]]:
    parsed = urlparse(source_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    try:
        safe_root = validate_public_http_url(root)
    except UnsafeUrlError:
        return [], None, {"adapter": "shopify_api", "status": "failed", "reason": "unsafe_url"}
    endpoint = f"{safe_root.rstrip('/')}/products.json"
    candidates: list[ProductCandidate] = []
    for page in range(1, max_pages + 1):
        try:
            await wait_for_domain_slot(endpoint)
            res = await client.get(endpoint, params={"limit": 250, "page": page}, follow_redirects=False)
        except httpx.HTTPError:
            return candidates, None, {"adapter": "shopify_api", "status": "failed", "reason": "network_error"}
        if res.status_code == 429:
            retry_after = res.headers.get("Retry-After", "").strip()
            record_domain_rate_limit(endpoint, int(retry_after) if retry_after.isdigit() else None)
            return candidates, None, {"adapter": "shopify_api", "status": "limited", "http_status": 429}
        if res.status_code == 403:
            return candidates, None, {"adapter": "shopify_api", "status": "blocked", "http_status": 403}
        if res.status_code in {404, 410}:
            return candidates, None, {"adapter": "shopify_api", "status": "not_applicable", "http_status": res.status_code}
        if res.status_code >= 400:
            return candidates, None, {"adapter": "shopify_api", "status": "failed", "http_status": res.status_code}
        try:
            data = res.json()
        except json.JSONDecodeError:
            return candidates, None, {"adapter": "shopify_api", "status": "not_applicable", "reason": "invalid_json"}
        products = data.get("products") if isinstance(data, dict) else None
        if not isinstance(products, list):
            return candidates, None, {"adapter": "shopify_api", "status": "not_applicable", "reason": "unexpected_payload"}
        record_domain_success(endpoint)
        for product in products:
            if not isinstance(product, dict) or not product.get("handle"):
                continue
            candidates.append(
                ProductCandidate(
                    f"{root}/products/{product['handle']}",
                    product.get("title"),
                    {"kind": "shopify_product", "product": product},
                    ("shopify_api",),
                )
            )
        if len(products) < 250:
            return candidates, len(candidates), {"adapter": "shopify_api", "status": "available", "http_status": res.status_code}
    return candidates, None, {"adapter": "shopify_api", "status": "failed", "reason": "page_limit_reached"}


async def woocommerce_catalog_discovery(
    client: httpx.AsyncClient,
    source_url: str,
    max_pages: int = 20,
) -> tuple[list[ProductCandidate], int | None, dict[str, Any]]:
    parsed = urlparse(source_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    try:
        safe_root = validate_public_http_url(root)
    except UnsafeUrlError:
        return [], None, {"adapter": "woocommerce_store_api", "status": "failed", "reason": "unsafe_url"}
    endpoint = f"{safe_root.rstrip('/')}/wp-json/wc/store/v1/products"
    candidates: list[ProductCandidate] = []
    reference_count: int | None = None
    for page in range(1, max_pages + 1):
        try:
            await wait_for_domain_slot(endpoint)
            res = await client.get(endpoint, params={"per_page": 100, "page": page}, follow_redirects=False)
        except httpx.HTTPError:
            return candidates, reference_count, {"adapter": "woocommerce_store_api", "status": "failed", "reason": "network_error"}
        if res.status_code == 429:
            retry_after = res.headers.get("Retry-After", "").strip()
            record_domain_rate_limit(endpoint, int(retry_after) if retry_after.isdigit() else None)
            return candidates, reference_count, {"adapter": "woocommerce_store_api", "status": "limited", "http_status": 429}
        if res.status_code == 403:
            return candidates, reference_count, {"adapter": "woocommerce_store_api", "status": "blocked", "http_status": 403}
        if res.status_code in {404, 410}:
            return candidates, None, {"adapter": "woocommerce_store_api", "status": "not_applicable", "http_status": res.status_code}
        if res.status_code >= 400:
            return candidates, reference_count, {"adapter": "woocommerce_store_api", "status": "failed", "http_status": res.status_code}
        try:
            products = res.json()
        except json.JSONDecodeError:
            return candidates, None, {"adapter": "woocommerce_store_api", "status": "not_applicable", "reason": "invalid_json"}
        if not isinstance(products, list):
            return candidates, None, {"adapter": "woocommerce_store_api", "status": "not_applicable", "reason": "unexpected_payload"}
        record_domain_success(endpoint)
        if page == 1 and res.headers.get("X-WP-Total", "").isdigit():
            reference_count = int(res.headers["X-WP-Total"])
        candidates.extend(woocommerce_product_candidates_from_payload(products, source_url))
        total_pages = res.headers.get("X-WP-TotalPages", "")
        if len(products) < 100 or (total_pages.isdigit() and page >= int(total_pages)):
            return candidates, reference_count, {"adapter": "woocommerce_store_api", "status": "available", "http_status": res.status_code}
    return candidates, reference_count, {"adapter": "woocommerce_store_api", "status": "failed", "reason": "page_limit_reached"}


async def discover_catalog(
    source_url: str,
    limit: int = 1000,
    include_keywords: Sequence[str] | None = None,
    exclude_keywords: Sequence[str] | None = None,
    use_sitemap: bool = True,
    require_relevance: bool = True,
    selector: str | None = None,
) -> CatalogDiscoveryResult:
    source_url = normalize_url(source_url)
    parsed = urlparse(source_url)
    sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
    include = include_keywords or []
    exclude = exclude_keywords or []
    candidates: list[ProductCandidate] = []
    attempts: list[dict[str, Any]] = []
    reference_counts: list[int] = []
    headers = {"user-agent": "Mozilla/5.0 ProductIntelligenceMonitor/1.0 (+local monitoring tool)"}
    async with httpx.AsyncClient(timeout=20, headers=headers) as client:
        shopify_candidates, shopify_reference, shopify_attempt = await shopify_catalog_discovery(client, source_url)
        candidates.extend(shopify_candidates)
        attempts.append(shopify_attempt)
        if shopify_reference is not None:
            reference_counts.append(shopify_reference)

        woocommerce_candidates, woocommerce_reference, woocommerce_attempt = await woocommerce_catalog_discovery(client, source_url)
        candidates.extend(woocommerce_candidates)
        attempts.append(woocommerce_attempt)
        if woocommerce_reference is not None:
            reference_counts.append(woocommerce_reference)

        if use_sitemap:
            candidates.extend(await discover_sitemap_candidates(client, source_url, sitemap_url))

        page = await fetch_text(client, source_url)
        if page:
            lowered = page[:300].lower()
            if "<?xml" in lowered or "<rss" in lowered or "<urlset" in lowered or "<feed" in lowered:
                candidates.extend(with_discovery_source(xml_candidates(page, source_url), "sitemap"))
            else:
                page_candidates = html_candidates(page, source_url, selector)
                candidates.extend(with_discovery_source(page_candidates, "html_links"))
                candidates.extend(jsonld_item_list_candidates(page, source_url))
                collection_seeds = [ProductCandidate(source_url), *page_candidates]
                candidates.extend(await discover_collection_candidates(client, source_url, collection_seeds))

    filtered = [
        candidate
        for candidate in candidates
        if same_domain(source_url, candidate.url)
        and matches_catalog_candidate_rules(candidate, include, exclude, require_relevance)
        and candidate_is_confirmed_product(candidate)
    ]
    if len(filtered) < 10:
        rendered = await rendered_candidates(source_url, selector)
        filtered.extend(
            candidate
            for candidate in with_discovery_source(rendered, "browser_render")
            if same_domain(source_url, candidate.url)
            and matches_catalog_candidate_rules(candidate, include, exclude, require_relevance)
            and candidate_is_confirmed_product(candidate)
        )
    merged = merge_catalog_candidates(sorted(filtered, key=candidate_priority), limit)
    return CatalogDiscoveryResult(
        candidates=merged,
        reference_count=max(reference_counts) if reference_counts else None,
        discovery_source_counts=discovery_source_counts(merged),
        adapter_attempts=attempts,
    )


async def discover_candidates(
    source_url: str,
    limit: int = 1000,
    include_keywords: Sequence[str] | None = None,
    exclude_keywords: Sequence[str] | None = None,
    use_sitemap: bool = True,
    require_relevance: bool = True,
    selector: str | None = None,
) -> list[ProductCandidate]:
    return (await discover_catalog(
        source_url,
        limit=limit,
        include_keywords=include_keywords,
        exclude_keywords=exclude_keywords,
        use_sitemap=use_sitemap,
        require_relevance=require_relevance,
        selector=selector,
    )).candidates


async def shopify_product_candidates(client: httpx.AsyncClient, source_url: str, max_pages: int = 20) -> list[ProductCandidate]:
    candidates, _, _ = await shopify_catalog_discovery(client, source_url, max_pages=max_pages)
    return candidates


async def extract_source_text(url: str, selector: str | None = None) -> ExtractedSourceText | None:
    url = normalize_url(url)
    headers = {
        "user-agent": "Mozilla/5.0 ProductIntelligenceMonitor/1.0 (+local monitoring tool)"
    }
    async with httpx.AsyncClient(timeout=20, headers=headers) as client:
        document = await fetch_document(client, url)
    if not document:
        return None

    content = document.content
    capture_method = "http"

    soup = BeautifulSoup(content, "xml" if content[:300].lower().lstrip().startswith("<?xml") else "lxml")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    roots = [soup]
    if selector:
        try:
            selected = soup.select(selector)
            if selected:
                roots = selected
        except Exception:
            roots = [soup]

    fragments: list[str] = []
    for root in roots:
        for fragment in root.stripped_strings:
            text_fragment = clean_text(fragment)
            if text_fragment:
                fragments.append(text_fragment)
    text = "\n".join(fragments)
    if len(text) < 200 and not content[:300].lower().lstrip().startswith("<?xml"):
        rendered = await try_render_page(url, selector=selector)
        if rendered and rendered.text.strip():
            content = rendered.html
            text = rendered.text
            capture_method = "browser_render"
            document = FetchedDocument(
                url=rendered.url or document.url,
                content=content,
                status_code=rendered.status_code or document.status_code,
                content_type="text/html",
            )
    return ExtractedSourceText(
        url=document.url,
        selector=selector,
        text=text[:12000],
        content_hash=hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest(),
        text_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        capture_method=capture_method,
        http_status=document.status_code,
        content_type=document.content_type,
        content_length=len(content.encode("utf-8", errors="ignore")),
    )


def meta_content(soup: BeautifulSoup, *selectors: str) -> str | None:
    for selector in selectors:
        tag = soup.select_one(selector)
        if tag and tag.get("content"):
            return unescape(tag["content"]).strip()
    return None


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def currency_symbol(currency: str | None) -> str:
    symbols = {
        "USD": "$",
        "CNY": "¥",
        "RMB": "¥",
        "EUR": "€",
        "GBP": "£",
        "JPY": "¥",
    }
    return symbols.get((currency or "").upper(), f"{currency} " if currency else "$")


def parse_money(value: Any) -> float | None:
    if value is None:
        return None
    match = re.search(r"\d+(?:[,.]\d+)?", str(value))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def normalized_identifier(kind: str, value: Any) -> str | None:
    raw = clean_text(str(value or ""))
    if not raw:
        return None
    if kind == "gtin":
        digits = re.sub(r"\D", "", raw)
        return digits or None
    if kind == "sku":
        return raw.upper()
    return raw


def format_money(value: float, currency: str | None = None) -> str:
    symbol = currency_symbol(currency)
    amount = f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{symbol}{amount}" if len(symbol) == 1 else f"{symbol}{amount}".strip()


def format_price_range(values: Sequence[float], currency: str | None = None) -> str | None:
    clean_values = sorted({value for value in values if value is not None})
    if not clean_values:
        return None
    if len(clean_values) == 1:
        return format_money(clean_values[0], currency)
    return f"{format_money(clean_values[0], currency)} - {format_money(clean_values[-1], currency)}"


def normalize_currency(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    if text in {"RMB", "CN¥"}:
        return "CNY"
    if len(text) == 3 and text.isalpha():
        return text
    return text[:12]


def normalize_availability(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if "instock" in text or "in stock" in text or text == "true":
        return "in_stock"
    if "outofstock" in text or "out of stock" in text or text == "false":
        return "out_of_stock"
    if "preorder" in text or "pre-order" in text:
        return "preorder"
    if "backorder" in text:
        return "backorder"
    if "soldout" in text or "sold out" in text:
        return "out_of_stock"
    return None


def extract_price(text: str) -> str | None:
    patterns = [
        r"(?:￥|¥|CNY\s*)\s?\d+(?:[,.]\d{1,2})?",
        r"(?:\$|USD\s*)\s?\d+(?:[,.]\d{1,2})?",
        r"\d+(?:[,.]\d{1,2})?\s?(?:元|RMB)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return match.group(0)
    return None


def flatten_jsonld(value: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            items.extend(flatten_jsonld(item))
    elif isinstance(value, dict):
        items.append(value)
        if value.get("@graph"):
            items.extend(flatten_jsonld(value["@graph"]))
    return items


def jsonld_type_matches(item: dict[str, Any], expected: str) -> bool:
    value = item.get("@type")
    if isinstance(value, list):
        return any(str(part).lower() == expected for part in value)
    return str(value).lower() == expected


def price_from_offer(offer: Any) -> tuple[float | None, float | None, str | None]:
    if isinstance(offer, list):
        lows: list[float] = []
        highs: list[float] = []
        currency = None
        for item in offer:
            low, high, item_currency = price_from_offer(item)
            if low is not None:
                lows.append(low)
            if high is not None:
                highs.append(high)
            currency = currency or item_currency
        values = lows + highs
        return (min(values), max(values), currency) if values else (None, None, currency)
    if not isinstance(offer, dict):
        return None, None, None
    currency = offer.get("priceCurrency")
    low = parse_money(offer.get("lowPrice") or offer.get("price"))
    high = parse_money(offer.get("highPrice") or offer.get("price"))
    return low, high, currency


def availability_from_offer(offer: Any) -> str | None:
    if isinstance(offer, list):
        statuses = [availability_from_offer(item) for item in offer]
        statuses = [status for status in statuses if status]
        if "in_stock" in statuses:
            return "in_stock"
        return statuses[0] if statuses else None
    if not isinstance(offer, dict):
        return None
    return normalize_availability(offer.get("availability"))


def extract_structured_price(soup: BeautifulSoup) -> dict[str, Any]:
    result: dict[str, Any] = {
        "price": None,
        "price_amount": None,
        "currency": None,
        "compare_at_price": None,
        "availability": None,
        "variant_count": None,
    }
    for script in soup.find_all("script", type=lambda value: value and "ld+json" in value):
        try:
            data = json.loads(script.string or script.get_text() or "")
        except json.JSONDecodeError:
            continue
        for item in flatten_jsonld(data):
            if not jsonld_type_matches(item, "product"):
                continue
            low, high, currency = price_from_offer(item.get("offers"))
            values = [value for value in (low, high) if value is not None]
            if values:
                result["price"] = format_price_range(values, currency)
                result["price_amount"] = min(values)
                result["currency"] = normalize_currency(currency)
                result["availability"] = availability_from_offer(item.get("offers"))
                return result

    amount = meta_content(
        soup,
        'meta[property="product:price:amount"]',
        'meta[property="og:price:amount"]',
    )
    if amount:
        parsed = parse_money(amount)
        if parsed is not None:
            currency = meta_content(
                soup,
                'meta[property="product:price:currency"]',
                'meta[property="og:price:currency"]',
            )
            availability = meta_content(
                soup,
                'meta[property="product:availability"]',
                'meta[property="og:availability"]',
            )
            result["price"] = format_money(parsed, currency)
            result["price_amount"] = parsed
            result["currency"] = normalize_currency(currency)
            result["availability"] = normalize_availability(availability)
    return result


def has_jsonld_product(soup: BeautifulSoup) -> bool:
    for script in soup.find_all("script", type=lambda value: value and "ld+json" in value):
        try:
            data = json.loads(script.string or script.get_text() or "")
        except json.JSONDecodeError:
            continue
        if any(jsonld_type_matches(item, "product") for item in flatten_jsonld(data)):
            return True
    return False


def extraction_quality(
    *,
    title: str | None,
    description: str | None,
    image_url: str | None,
    price: str | None,
    features: Sequence[str],
    extraction_source: str,
) -> tuple[float, dict[str, float], list[str]]:
    source_base = {
        "shopify_api": 0.9,
        "woocommerce_store_api": 0.88,
        "json_ld": 0.82,
        "meta_tags": 0.72,
        "browser_render": 0.68,
        "html_inference": 0.58,
    }.get(extraction_source, 0.5)
    field_confidence = {
        "title": 0.95 if title else 0.0,
        "description": 0.85 if description and len(description) >= 40 else (0.55 if description else 0.0),
        "image": 0.8 if image_url else 0.0,
        "price": 0.85 if price else 0.0,
        "features": min(0.9, 0.45 + len(features[:5]) * 0.09) if features else 0.0,
    }
    completeness = sum(field_confidence.values()) / len(field_confidence)
    score = round(min(0.98, max(0.05, source_base * 0.65 + completeness * 0.35)), 2)
    reasons = [f"来源：{extraction_source}"]
    missing = [
        label
        for key, label in {
            "price": "价格",
            "image": "图片",
            "features": "卖点",
            "description": "描述",
        }.items()
        if field_confidence[key] == 0
    ]
    if missing:
        reasons.append("缺少：" + "、".join(missing))
    if score < 0.7:
        reasons.append("低置信度，建议人工复核")
    return score, field_confidence, reasons


def extract_features(soup: BeautifulSoup, raw_text: str) -> list[str]:
    features: list[str] = []
    content_root = soup.select_one("main, [role='main'], #MainContent, [id*='product']") or soup.body or soup
    navigation_labels = {
        "best sellers",
        "back to school",
        "discover",
        "products",
        "shop all",
        "new arrivals",
    }

    for item in content_root.select("li"):
        text = clean_text(item.get_text(" ", strip=True))
        if 8 <= len(text) <= 180 and text.lower() not in navigation_labels and text not in features:
            features.append(text)
        if len(features) >= 8:
            return features

    if not features:
        for item in content_root.select("[class*=feature], [class*=highlight], [class*=spec], [class*=benefit]"):
            text = clean_text(item.get_text(" ", strip=True))
            if 8 <= len(text) <= 180 and text.lower() not in navigation_labels and text not in features:
                features.append(text)
            if len(features) >= 8:
                return features

    content_text = clean_text(content_root.get_text(" ", strip=True)) or raw_text
    sentences = re.split(r"(?<=[。.!?])\s+", content_text)
    for sentence in sentences:
        text = clean_text(sentence)
        lowered = text.lower()
        if 12 <= len(text) <= 180 and any(hint in lowered for hint in FEATURE_HINTS):
            if text not in features:
                features.append(text)
        if len(features) >= 8:
            break
    return features


def product_from_shopify_payload(candidate: ProductCandidate) -> ExtractedProduct | None:
    payload = candidate.payload or {}
    if payload.get("kind") != "shopify_product":
        return None
    product = payload.get("product")
    if not isinstance(product, dict):
        return None

    title = clean_text(product.get("title") or candidate.title_hint or candidate.url)
    body_html = product.get("body_html") or ""
    body_soup = BeautifulSoup(body_html, "lxml")
    raw_text = clean_text(body_soup.get_text(" ", strip=True))
    description = raw_text[:1000]

    variants = product.get("variants") if isinstance(product.get("variants"), list) else []
    option_names = [
        clean_text(str(option.get("name")))
        for option in product.get("options", [])
        if isinstance(option, dict) and clean_text(str(option.get("name") or ""))
    ]
    extracted_variants: list[ExtractedVariant] = []
    identifiers: list[ExtractedIdentifier] = []
    product_external_id = normalized_identifier("platform_product_id", product.get("id"))
    if product_external_id:
        identifiers.append(ExtractedIdentifier("platform_product_id", product_external_id, str(product.get("id")), "shopify_product"))
    for index, variant in enumerate(variants):
        if not isinstance(variant, dict):
            continue
        raw_external_id = variant.get("id") or variant.get("sku") or variant.get("title") or str(index + 1)
        option_values = [
            f"{option_name}: {clean_text(str(variant.get(f'option{position}') or ''))}"
            for position, option_name in enumerate(option_names, start=1)
            if clean_text(str(variant.get(f"option{position}") or ""))
        ]
        price_amount = parse_money(variant.get("price"))
        compare_at_price = parse_money(variant.get("compare_at_price"))
        extracted_variants.append(
            ExtractedVariant(
                external_id=str(raw_external_id),
                sku=clean_text(str(variant.get("sku") or "")) or None,
                title=clean_text(str(variant.get("title") or "")) or None,
                option_values=option_values,
                price=format_money(price_amount) if price_amount is not None else None,
                price_amount=price_amount,
                compare_at_price=compare_at_price,
                availability="in_stock" if variant.get("available") is True else ("out_of_stock" if variant.get("available") is False else None),
            )
        )
        for kind, raw_identifier in (("sku", variant.get("sku")), ("gtin", variant.get("barcode")), ("platform_variant_id", variant.get("id"))):
            normalized = normalized_identifier(kind, raw_identifier)
            if normalized:
                identifiers.append(ExtractedIdentifier(kind, normalized, str(raw_identifier), "shopify_variant"))
    prices = [
        parsed
        for parsed in (parse_money(variant.get("price")) for variant in variants if isinstance(variant, dict))
        if parsed is not None
    ]
    compare_prices = [
        parsed
        for parsed in (parse_money(variant.get("compare_at_price")) for variant in variants if isinstance(variant, dict))
        if parsed is not None
    ]
    price = format_price_range(prices)
    price_amount = min(prices) if prices else None
    compare_at_price = min([value for value in compare_prices if price_amount is None or value > price_amount], default=None)
    available_values = [
        variant.get("available")
        for variant in variants
        if isinstance(variant, dict) and variant.get("available") is not None
    ]
    if any(value is True for value in available_values):
        availability = "in_stock"
    elif available_values and all(value is False for value in available_values):
        availability = "out_of_stock"
    else:
        availability = None
    variant_count = len(variants) or None

    images = product.get("images") if isinstance(product.get("images"), list) else []
    image_url = None
    if images and isinstance(images[0], dict):
        image_url = images[0].get("src")

    tags = product.get("tags") if isinstance(product.get("tags"), list) else []
    features = [clean_text(str(tag)) for tag in tags if clean_text(str(tag))][:8]
    if not features:
        features = extract_features(body_soup, raw_text)

    hash_source = json.dumps(
        {
            "title": title,
            "description": description,
            "price": price,
            "updated_at": product.get("updated_at"),
            "variants": variants,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    confidence_score, field_confidence, confidence_reasons = extraction_quality(
        title=title,
        description=description,
        image_url=image_url,
        price=price,
        features=features,
        extraction_source="shopify_api",
    )
    return ExtractedProduct(
        url=candidate.url,
        title=title[:300],
        description=description,
        image_url=image_url,
        price=price,
        price_amount=price_amount,
        currency=None,
        compare_at_price=compare_at_price,
        availability=availability,
        variant_count=variant_count,
        variants=extracted_variants,
        features=features,
        extraction_source="shopify_api",
        confidence_score=confidence_score,
        field_confidence=field_confidence,
        confidence_reasons=confidence_reasons,
        content_hash=hashlib.sha256(hash_source.encode("utf-8")).hexdigest(),
        raw_text=raw_text[:4000],
        identifiers=identifiers,
    )


def woocommerce_price_amount(value: Any, minor_unit: Any) -> float | None:
    parsed = parse_money(value)
    if parsed is None:
        return None
    try:
        divisor = 10 ** int(minor_unit)
    except (TypeError, ValueError):
        divisor = 100
    return parsed / divisor


def product_from_woocommerce_payload(candidate: ProductCandidate) -> ExtractedProduct | None:
    payload = candidate.payload or {}
    if payload.get("kind") != "woocommerce_product":
        return None
    product = payload.get("product")
    if not isinstance(product, dict):
        return None
    title = clean_text(str(product.get("name") or candidate.title_hint or candidate.url))
    description_html = str(product.get("description") or product.get("short_description") or product.get("summary") or "")
    description_soup = BeautifulSoup(description_html, "lxml")
    description = clean_text(description_soup.get_text(" ", strip=True))[:1000]
    prices = product.get("prices") if isinstance(product.get("prices"), dict) else {}
    currency = normalize_currency(prices.get("currency_code"))
    price_amount = woocommerce_price_amount(prices.get("price"), prices.get("currency_minor_unit"))
    compare_at_price = woocommerce_price_amount(prices.get("regular_price"), prices.get("currency_minor_unit"))
    if compare_at_price is not None and price_amount is not None and compare_at_price <= price_amount:
        compare_at_price = None
    images = product.get("images") if isinstance(product.get("images"), list) else []
    image_url = next((image.get("src") for image in images if isinstance(image, dict) and image.get("src")), None)
    stock_status = str(product.get("stock_status") or "").lower()
    availability = "in_stock" if product.get("is_in_stock") is True or stock_status in {"instock", "onbackorder"} else ("out_of_stock" if product.get("is_in_stock") is False or stock_status == "outofstock" else None)
    features = [
        clean_text(str(item.get("name") or ""))
        for item in product.get("categories", [])
        if isinstance(item, dict) and clean_text(str(item.get("name") or ""))
    ][:4]
    identifiers: list[ExtractedIdentifier] = []
    for kind, raw_identifier in (("platform_product_id", product.get("id")), ("sku", product.get("sku"))):
        normalized = normalized_identifier(kind, raw_identifier)
        if normalized:
            identifiers.append(ExtractedIdentifier(kind, normalized, str(raw_identifier), "woocommerce_store_api"))
    hash_source = json.dumps(product, ensure_ascii=False, sort_keys=True, default=str)
    confidence_score, field_confidence, confidence_reasons = extraction_quality(
        title=title,
        description=description,
        image_url=image_url,
        price=format_money(price_amount, currency) if price_amount is not None else None,
        features=features,
        extraction_source="woocommerce_store_api",
    )
    return ExtractedProduct(
        url=candidate.url,
        title=title[:300],
        description=description,
        image_url=image_url,
        price=format_money(price_amount, currency) if price_amount is not None else None,
        price_amount=price_amount,
        currency=currency,
        compare_at_price=compare_at_price,
        availability=availability,
        variant_count=None,
        variants=[],
        features=features,
        extraction_source="woocommerce_store_api",
        confidence_score=confidence_score,
        field_confidence=field_confidence,
        confidence_reasons=confidence_reasons,
        content_hash=hashlib.sha256(hash_source.encode("utf-8")).hexdigest(),
        raw_text=description,
        identifiers=identifiers,
    )


async def extract_candidate_product(candidate: ProductCandidate) -> ExtractedProduct | None:
    from_payload = product_from_shopify_payload(candidate) or product_from_woocommerce_payload(candidate)
    if from_payload:
        return from_payload
    return await extract_product(candidate.url, candidate.title_hint)


def product_from_html(url: str, html: str, title_hint: str | None = None, rendered: bool = False) -> ExtractedProduct:
    soup = BeautifulSoup(html, "lxml")
    has_structured_product = has_jsonld_product(soup)
    structured_price = extract_structured_price(soup)
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    title = meta_content(soup, 'meta[property="og:title"]', 'meta[name="twitter:title"]')
    title_from_meta = bool(title)
    if not title and soup.h1:
        title = clean_text(soup.h1.get_text(" ", strip=True))
    if not title:
        title = clean_text(soup.title.get_text(" ", strip=True)) if soup.title else title_hint
    title = title or title_hint or url

    description = (
        meta_content(soup, 'meta[name="description"]', 'meta[property="og:description"]')
        or ""
    )
    description_from_meta = bool(description)
    image = meta_content(soup, 'meta[property="og:image"]', 'meta[name="twitter:image"]')
    if image:
        image = urljoin(url, image)

    raw_text = clean_text(soup.get_text(" ", strip=True))
    if not description:
        description = raw_text[:500]

    price = structured_price.get("price")
    features = extract_features(soup, raw_text)
    extraction_source = "json_ld" if has_structured_product else ("meta_tags" if title_from_meta or image or description_from_meta else "html_inference")
    if rendered and extraction_source == "html_inference":
        extraction_source = "browser_render"
    confidence_score, field_confidence, confidence_reasons = extraction_quality(
        title=title,
        description=description,
        image_url=image,
        price=price,
        features=features,
        extraction_source=extraction_source,
    )
    hash_source = f"{title}\n{description}\n{raw_text[:2000]}"
    content_hash = hashlib.sha256(hash_source.encode("utf-8")).hexdigest()

    return ExtractedProduct(
        url=url,
        title=title[:300],
        description=description[:1000],
        image_url=image,
        price=price,
        price_amount=structured_price.get("price_amount"),
        currency=structured_price.get("currency"),
        compare_at_price=structured_price.get("compare_at_price"),
        availability=structured_price.get("availability"),
        variant_count=structured_price.get("variant_count"),
        variants=[],
        features=features,
        extraction_source=extraction_source,
        confidence_score=confidence_score,
        field_confidence=field_confidence,
        confidence_reasons=confidence_reasons,
        content_hash=content_hash,
        raw_text=raw_text[:4000],
    )


async def extract_product(url: str, title_hint: str | None = None) -> ExtractedProduct | None:
    headers = {
        "user-agent": "Mozilla/5.0 ProductIntelligenceMonitor/1.0 (+local monitoring tool)"
    }
    async with httpx.AsyncClient(timeout=20, headers=headers) as client:
        fetch_result = await fetch_product_result(client, url)
    raise_for_fetch_failure(fetch_result)
    html = fetch_result.content

    product = product_from_html(url, html, title_hint) if html else None
    if product and product.confidence_score >= 0.7:
        return product

    rendered = await try_render_page(url)
    if not rendered or not rendered.html:
        return product

    rendered_product = product_from_html(rendered.url or url, rendered.html, title_hint, rendered=True)
    if not product:
        return rendered_product
    if rendered_product.confidence_score > product.confidence_score:
        return rendered_product
    if not product.price and rendered_product.price:
        return rendered_product
    return product
