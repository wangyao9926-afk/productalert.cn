from __future__ import annotations

import unittest
from pathlib import Path


class ProductVariantsUiTests(unittest.TestCase):
    def test_product_detail_loads_and_renders_variant_level_records(self) -> None:
        api_source = Path("frontend/src/api/products.ts").read_text(encoding="utf-8")
        page_source = Path("frontend/src/features/products/ProductDetailPage.tsx").read_text(encoding="utf-8")

        self.assertIn('getJson<ProductVariant[]>(`/api/products/${product.id}/variants`)', api_source)
        self.assertIn("variants: ProductVariant[]", api_source)
        self.assertIn("is_active: boolean", api_source)
        monitor_source = Path("frontend/src/api/monitors.ts").read_text(encoding="utf-8")
        self.assertIn('"new-products": ["product_new", "variant_new"]', monitor_source)
        self.assertIn("data.variants", page_source)
        self.assertIn("VARIANTS", page_source)
        self.assertIn("已下架", page_source)
        detail_source = Path("frontend/src/features/changes/ChangeDetailPage.tsx").read_text(encoding="utf-8")
        self.assertIn("variant_price", detail_source)
        self.assertIn("变体价格", detail_source)
        self.assertIn("variant_added", detail_source)
        self.assertIn("新增变体", detail_source)


if __name__ == "__main__":
    unittest.main()
