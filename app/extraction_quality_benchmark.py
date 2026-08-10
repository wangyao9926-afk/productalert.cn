from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Sequence

from app.crawler import ProductCandidate, product_from_html, product_from_shopify_payload, product_from_woocommerce_payload


QUALITY_FIELDS = ("url", "title", "price_amount", "currency", "availability", "variant_count")


@dataclass(frozen=True)
class BenchmarkCase:
    name: str
    url: str
    expected: dict[str, Any]
    html: str | None = None
    payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class BenchmarkCaseResult:
    name: str
    passed: bool
    mismatches: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class BenchmarkReport:
    passed: bool
    case_results: list[BenchmarkCaseResult]
    field_pass_rates: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "case_results": [
                {"name": result.name, "passed": result.passed, "mismatches": result.mismatches}
                for result in self.case_results
            ],
            "field_pass_rates": self.field_pass_rates,
        }


def extract_case(case: BenchmarkCase):
    candidate = ProductCandidate(url=case.url, payload=case.payload)
    if case.payload is not None:
        return product_from_shopify_payload(candidate) or product_from_woocommerce_payload(candidate)
    if case.html is None:
        raise ValueError(f"Benchmark case '{case.name}' requires html or payload")
    return product_from_html(case.url, case.html)


def run_benchmark(cases: Sequence[BenchmarkCase]) -> BenchmarkReport:
    field_totals = {field: 0 for field in QUALITY_FIELDS}
    field_matches = {field: 0 for field in QUALITY_FIELDS}
    case_results: list[BenchmarkCaseResult] = []

    for case in cases:
        product = extract_case(case)
        actual = {field: getattr(product, field) if product else None for field in QUALITY_FIELDS}
        mismatches: dict[str, dict[str, Any]] = {}
        for field, expected in case.expected.items():
            if field not in QUALITY_FIELDS:
                raise ValueError(f"Unsupported benchmark field: {field}")
            field_totals[field] += 1
            if actual[field] == expected:
                field_matches[field] += 1
            else:
                mismatches[field] = {"expected": expected, "actual": actual[field]}
        case_results.append(BenchmarkCaseResult(name=case.name, passed=not mismatches, mismatches=mismatches))

    field_pass_rates = {
        field: field_matches[field] / field_totals[field]
        for field in QUALITY_FIELDS
        if field_totals[field]
    }
    return BenchmarkReport(
        passed=all(result.passed for result in case_results),
        case_results=case_results,
        field_pass_rates=field_pass_rates,
    )


def default_cases() -> list[BenchmarkCase]:
    return [
        BenchmarkCase(
            name="shopify-two-variants",
            url="https://benchmark.example.com/products/trail-pack",
            payload={
                "kind": "shopify_product",
                "product": {
                    "title": "Trail Pack",
                    "body_html": "<p>A weather-ready carry pack for daily travel.</p>",
                    "variants": [
                        {"price": "39.00", "compare_at_price": "49.00", "available": True},
                        {"price": "45.00", "compare_at_price": "55.00", "available": False},
                    ],
                    "images": [{"src": "https://cdn.example.com/trail-pack.jpg"}],
                    "tags": ["weather-ready", "carry-on"],
                    "updated_at": "2026-07-30T00:00:00Z",
                },
            },
            expected={
                "url": "https://benchmark.example.com/products/trail-pack",
                "title": "Trail Pack",
                "price_amount": 39.0,
                "availability": "in_stock",
                "variant_count": 2,
            },
        ),
        BenchmarkCase(
            name="jsonld-aggregate-offer",
            url="https://benchmark.example.com/products/arc-lamp",
            html="""
                <html><head>
                  <title>Arc Lamp</title>
                  <script type="application/ld+json">
                    {"@context":"https://schema.org","@type":"Product","name":"Arc Lamp",
                     "offers":{"@type":"AggregateOffer","lowPrice":"110.00","highPrice":"130.00",
                     "priceCurrency":"USD","availability":"https://schema.org/OutOfStock"}}
                  </script>
                </head><body><h1>Arc Lamp</h1></body></html>
            """,
            expected={
                "url": "https://benchmark.example.com/products/arc-lamp",
                "title": "Arc Lamp",
                "price_amount": 110.0,
                "currency": "USD",
                "availability": "out_of_stock",
            },
        ),
        BenchmarkCase(
            name="woocommerce-public-catalog-product",
            url="https://benchmark.example.com/shop/quiet-pump",
            payload={
                "kind": "woocommerce_product",
                "product": {
                    "id": 77,
                    "name": "Quiet Pump",
                    "sku": "QP-77",
                    "description": "<p>Compact pump for outdoor equipment.</p>",
                    "images": [{"src": "https://cdn.example.com/quiet-pump.jpg"}],
                    "is_in_stock": True,
                    "prices": {
                        "price": "2599",
                        "regular_price": "2999",
                        "currency_code": "USD",
                        "currency_minor_unit": 2,
                    },
                },
            },
            expected={
                "url": "https://benchmark.example.com/shop/quiet-pump",
                "title": "Quiet Pump",
                "price_amount": 25.99,
                "currency": "USD",
                "availability": "in_stock",
            },
        ),
    ]


def controlled_benchmark_summary() -> dict[str, Any]:
    report = run_benchmark(default_cases())
    return {
        "scope": "controlled_fixture",
        "case_count": len(report.case_results),
        "passed": report.passed,
        "field_pass_rates": report.field_pass_rates,
        "case_results": [
            {"name": result.name, "passed": result.passed, "mismatches": result.mismatches}
            for result in report.case_results
        ],
        "coverage": ["shopify_api", "json_ld", "woocommerce_store_api"],
        "limitation": "这是受控样本回归测试，不代表线上真实站点的抓取准确率；真实准确率需要人工标注的站点真值集。",
    }


def main() -> None:
    summary = controlled_benchmark_summary()
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    raise SystemExit(0 if summary["passed"] else 1)


if __name__ == "__main__":
    main()
