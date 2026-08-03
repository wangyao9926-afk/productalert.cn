from __future__ import annotations

import unittest
from pathlib import Path


class PriceMatrixUiTests(unittest.TestCase):
    def test_price_matrix_has_a_verified_groups_api_and_route(self) -> None:
        api_source = Path("frontend/src/api/products.ts").read_text(encoding="utf-8")
        page_source = Path("frontend/src/features/intelligence/PriceMatrixPage.tsx").read_text(encoding="utf-8")
        routes_source = Path("frontend/src/app/routes.tsx").read_text(encoding="utf-8")

        self.assertIn('getJson<ProductMatchGroup[]>("/api/product-match-groups")', api_source)
        self.assertIn("loadPriceMatrix", api_source)
        self.assertIn("价格矩阵", page_source)
        self.assertIn("identifier_value", page_source)
        self.assertIn('path="/price-matrix"', routes_source)


if __name__ == "__main__":
    unittest.main()
