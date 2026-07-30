from __future__ import annotations

import unittest
from pathlib import Path


class ProductVariantsUiTests(unittest.TestCase):
    def test_product_detail_loads_and_renders_variant_level_records(self) -> None:
        api_source = Path("frontend/src/api/products.ts").read_text(encoding="utf-8")
        page_source = Path("frontend/src/features/products/ProductDetailPage.tsx").read_text(encoding="utf-8")

        self.assertIn('getJson<ProductVariant[]>(`/api/products/${product.id}/variants`)', api_source)
        self.assertIn("variants: ProductVariant[]", api_source)
        self.assertIn("data.variants", page_source)
        self.assertIn("VARIANTS", page_source)


if __name__ == "__main__":
    unittest.main()
