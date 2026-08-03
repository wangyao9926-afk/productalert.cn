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

from app.rate_limit import wait_for_domain_slot
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
    product_markers = ("products", "product")

    if any(segment in product_markers for segment in segments) and len(segments) >= 2:
        return "product_detail", "confirmed"
    if any(marker in joined for marker in promo_markers):
        return "promo_page", "false_positive"
    if any(segment in collection_markers for segment in segments):
        return "collection_page", "false_positive"
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
            if result.error_category:
                return result
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
        if "products" in segments:
            index = segments.index("products")
            if index + 1 < len(segments):
                return f"{parsed.netloc.lower().removeprefix('www.')}/products/{segments[index + 1].lower()}"
    return normalize_url(candidate.url)


def unique_urls(candidates: Iterable[ProductCandidate], limit: int) -> list[ProductCandidate]:
    seen: dict[str, int] = {}
    unique: list[ProductCandidate] = []
    for candidate in candidates:
        clean = candidate.url.split("#", 1)[0].rstrip("/")
        key = canonical_candidate_key(ProductCandidate(clean, candidate.title_hint, candidate.payload))
        if key in seen:
            index = seen[key]
            if candidate.payload and not unique[index].payload:
                unique[index] = ProductCandidate(clean, candidate.title_hint, candidate.payload)
            continue
        seen[key] = len(unique)
        unique.append(ProductCandidate(clean, candidate.title_hint, candidate.payload))
        if len(unique) >= limit:
            break
    return unique


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


async def discover_candidates(
    source_url: str,
    limit: int = 1000,
    include_keywords: Sequence[str] | None = None,
    exclude_keywords: Sequence[str] | None = None,
    use_sitemap: bool = True,
    require_relevance: bool = True,
    selector: str | None = None,
) -> list[ProductCandidate]:
    source_url = normalize_url(source_url)
    parsed = urlparse(source_url)
    sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
    include = include_keywords or []
    exclude = exclude_keywords or []
    candidates: list[ProductCandidate] = []

    headers = {
        "user-agent": "Mozilla/5.0 ProductIntelligenceMonitor/1.0 (+local monitoring tool)"
    }
    async with httpx.AsyncClient(timeout=20, headers=headers) as client:
        if use_sitemap:
            sitemap = await fetch_text(client, sitemap_url)
            if sitemap:
                sitemap_candidates = xml_candidates(sitemap, source_url)
                candidates.extend(sitemap_candidates)
                child_sitemaps = [
                    candidate
                    for candidate in sitemap_candidates
                    if same_domain(source_url, candidate.url) and looks_like_sitemap(candidate.url)
                ]
                for child in sorted(child_sitemaps, key=sitemap_priority)[:10]:
                    child_text = await fetch_text(client, child.url)
                    if child_text:
                        candidates.extend(xml_candidates(child_text, child.url))

        page = await fetch_text(client, source_url)
        if page:
            lowered = page[:300].lower()
            if "<?xml" in lowered or "<rss" in lowered or "<urlset" in lowered or "<feed" in lowered:
                candidates.extend(xml_candidates(page, source_url))
            else:
                candidates.extend(html_candidates(page, source_url, selector))

        candidates.extend(await shopify_product_candidates(client, source_url))

    same_site_candidates = [
        candidate for candidate in candidates if same_domain(source_url, candidate.url)
    ]
    filtered = [
        candidate
        for candidate in same_site_candidates
        if matches_keyword_rules(candidate, include, exclude, require_relevance)
    ]
    if len(filtered) < 10:
        rendered = await rendered_candidates(source_url, selector)
        if rendered:
            same_site_rendered = [
                candidate for candidate in rendered if same_domain(source_url, candidate.url)
            ]
            filtered.extend(
                candidate
                for candidate in same_site_rendered
                if matches_keyword_rules(candidate, include, exclude, require_relevance)
            )
    return unique_urls(sorted(filtered, key=candidate_priority), limit)


async def shopify_product_candidates(client: httpx.AsyncClient, source_url: str, max_pages: int = 20) -> list[ProductCandidate]:
    parsed = urlparse(source_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    try:
        safe_root = validate_public_http_url(root)
    except UnsafeUrlError:
        return []
    candidates: list[ProductCandidate] = []
    for page in range(1, max_pages + 1):
        try:
            await wait_for_domain_slot(f"{safe_root.rstrip('/')}/products.json")
            res = await client.get(f"{safe_root.rstrip('/')}/products.json", params={"limit": 250, "page": page}, follow_redirects=False)
            if res.status_code >= 400:
                break
            data = res.json()
        except (httpx.HTTPError, json.JSONDecodeError):
            break
        products = data.get("products") if isinstance(data, dict) else None
        if not products:
            break
        for product in products:
            handle = product.get("handle")
            if not handle:
                continue
            candidates.append(ProductCandidate(
                f"{root}/products/{handle}",
                product.get("title"),
                {"kind": "shopify_product", "product": product},
            ))
        if len(products) < 250:
            break
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
    for item in soup.select("li, [class*=feature], [class*=highlight], [class*=spec], [class*=benefit]"):
        text = clean_text(item.get_text(" ", strip=True))
        if 8 <= len(text) <= 180 and text not in features:
            features.append(text)
        if len(features) >= 8:
            return features

    sentences = re.split(r"(?<=[。.!?])\s+", raw_text)
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


async def extract_candidate_product(candidate: ProductCandidate) -> ExtractedProduct | None:
    from_payload = product_from_shopify_payload(candidate)
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
