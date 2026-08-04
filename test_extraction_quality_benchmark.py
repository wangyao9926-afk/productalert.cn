from __future__ import annotations

import unittest

from app.crawler import product_from_html
from app.extraction_quality_benchmark import BenchmarkCase, default_cases, run_benchmark


class ExtractionQualityBenchmarkTests(unittest.TestCase):
    def test_product_features_ignore_navigation_menu_items(self) -> None:
        product = product_from_html(
            "https://benchmark.example.com/products/orbit-pump",
            """
                <html><head><meta property="og:title" content="Orbit Pump"></head><body>
                  <header><nav><ul><li>BEST SELLERS</li><li>BACK TO SCHOOL</li></ul></nav></header>
                  <main><h1>Orbit Pump</h1><section class="product-features"><ul>
                    <li>Inflates a camping pad in 60 seconds</li>
                    <li>Only weighs 96 grams for backpacking</li>
                  </ul></section></main>
                  <footer><a>Shipping policy and support</a></footer>
                </body></html>
            """,
        )

        self.assertEqual(
            product.features,
            ["Inflates a camping pad in 60 seconds", "Only weighs 96 grams for backpacking"],
        )

    def test_report_counts_expected_html_product_fields(self) -> None:
        case = BenchmarkCase(
            name="json-ld-product",
            url="https://benchmark.example.com/products/orbit-bottle",
            html="""
                <html><head>
                  <script type="application/ld+json">
                    {"@context":"https://schema.org","@type":"Product","name":"Orbit Bottle",
                     "offers":{"@type":"Offer","price":"49.00","priceCurrency":"USD","availability":"https://schema.org/InStock"}}
                  </script>
                </head><body><h1>Orbit Bottle</h1></body></html>
            """,
            expected={
                "url": "https://benchmark.example.com/products/orbit-bottle",
                "title": "Orbit Bottle",
                "price_amount": 49.0,
                "currency": "USD",
                "availability": "in_stock",
            },
        )

        report = run_benchmark([case])

        self.assertTrue(report.passed)
        self.assertEqual(report.field_pass_rates["price_amount"], 1.0)
        self.assertEqual(report.field_pass_rates["availability"], 1.0)
        self.assertEqual(report.case_results[0].mismatches, {})

    def test_default_cases_cover_shopify_and_jsonld_price_stock_and_variants(self) -> None:
        report = run_benchmark(default_cases())

        self.assertTrue(report.passed)
        self.assertEqual(len(report.case_results), 2)
        self.assertEqual(report.field_pass_rates["price_amount"], 1.0)
        self.assertEqual(report.field_pass_rates["availability"], 1.0)
        self.assertEqual(report.field_pass_rates["variant_count"], 1.0)


if __name__ == "__main__":
    unittest.main()
