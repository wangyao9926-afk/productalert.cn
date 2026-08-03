# Variant Monitoring Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task with tests before implementation.

**Goal:** Persist Shopify product variants as stable records and make them available to the product-detail experience.

**Architecture:** Extend the existing extracted-product model with normalized variants from the Shopify adapter. A `product_variants` table uses the upstream variant id as its stable identity, and the current product-store flow synchronizes the records whenever a product is captured. A user-scoped API provides the records to the existing product detail page.

**Constraints:** No migration changes to existing tables; JSON-LD stays product-level until a source supplies real variant identities; tests are offline and TDD-first.

## Tasks

- [x] Extract normalized Shopify variant id, SKU, option title, price, compare-at price, and availability.
- [x] Add SQLite/PostgreSQL product-variant persistence and sync it during product capture.
- [x] Add owner-authorized variant listing and show the variants in product detail.
- [x] Run all verification, restart the preview, and publish the preview URL.
