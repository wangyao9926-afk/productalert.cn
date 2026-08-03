# Verified Product Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist verified product identifiers and create explainable cross-site same-product groups only for exact GTIN or SKU matches.

**Architecture:** Shopify extraction emits GTIN/barcode, SKU, and platform IDs. Product storage synchronizes identifier rows and refreshes exact GTIN/SKU match groups within the product owner's workspace. An owner-authorized API returns groups, and the product detail page presents matched records and their current price/availability.

**Tech Stack:** Python dataclasses, FastAPI, SQLite/PostgreSQL migrations, React/TypeScript, unittest.

## Global Constraints

- Only exact normalized GTIN or SKU values can create a cross-site match.
- Platform product/variant identifiers remain provenance-only.
- Products from one site alone never form a match group.
- All endpoints enforce the owning user's site boundary.

---

### Task 1: Extract and persist verified identifiers

**Files:**
- Modify: `app/crawler.py`
- Modify: `app/monitor.py`
- Create: `app/migrations/sqlite/007_product_identity.sql`
- Create: `app/migrations/postgresql/007_product_identity.sql`
- Test: `test_verified_product_identity.py`

**Interfaces:**
- `ExtractedProduct.identifiers: list[ExtractedIdentifier]`
- `sync_product_identifiers(db, product_id, product) -> None`

- [x] **Step 1: Write failing Shopify extraction and persistence tests**

```python
self.assertIn(("sku", "TRAIL-42"), {(item.kind, item.value) for item in product.identifiers})
self.assertIn(("gtin", "1234567890123"), persisted_identifiers)
```

- [x] **Step 2: Run the focused test and verify it fails because identity fields and tables are absent**

- [x] **Step 3: Add migrations, normalized identifier extraction, and product synchronization**

- [x] **Step 4: Re-run the focused test and verify it passes**

### Task 2: Build exact cross-site match groups and owner API

**Files:**
- Modify: `app/monitor.py`
- Modify: `app/main.py`
- Test: `test_verified_product_identity.py`

**Interfaces:**
- `refresh_product_match_groups(db, product_id) -> None`
- `GET /api/products/{product_id}/matches`

- [x] **Step 1: Write failing test for two sites with the same SKU, plus a different-user 404 check**

```python
self.assertEqual(response.json()[0]["identifier_value"], "TRAIL-42")
self.assertEqual(len(response.json()[0]["products"]), 2)
self.assertEqual(stranger.status_code, 404)
```

- [x] **Step 2: Run the focused test and verify it fails because no group/API exists**

- [x] **Step 3: Synchronize exact GTIN/SKU groups and add the owner API**

- [x] **Step 4: Re-run focused test and existing variant tests**

### Task 3: Show verified matches on the product page

**Files:**
- Modify: `frontend/src/api/products.ts`
- Modify: `frontend/src/features/products/ProductDetailPage.tsx`
- Test: `test_product_identity_ui.py`

- [x] **Step 1: Write a failing UI contract for `matches` and the “同款匹配” panel**
- [x] **Step 2: Add API loading and a compact panel with identifier, site, price, and availability**
- [x] **Step 3: Run full backend tests, API smoke, frontend build, UI contract test, restart previews, commit, and push**
