from __future__ import annotations

import unittest
from pathlib import Path


class ProductIdentityUiTests(unittest.TestCase):
    def test_product_detail_loads_and_renders_verified_same_product_matches(self) -> None:
        api_source = Path("frontend/src/api/products.ts").read_text(encoding="utf-8")
        page_source = Path("frontend/src/features/products/ProductDetailPage.tsx").read_text(encoding="utf-8")

        self.assertIn('getJson<ProductMatchGroup[]>(`/api/products/${product.id}/matches`)', api_source)
        self.assertIn("matches: ProductMatchGroup[]", api_source)
        self.assertIn("同款匹配", page_source)
        self.assertIn("data.matches", page_source)
        self.assertIn("identifier_value", page_source)


if __name__ == "__main__":
    unittest.main()
