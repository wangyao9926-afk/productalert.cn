# Extraction Quality Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic offline quality gate for product identity, price, availability, and variant extraction.

**Architecture:** Compact fixture documents have explicit expected fields. A benchmark module invokes the existing HTML and Shopify extractors, produces per-case results plus per-field pass rates, and exits non-zero on a mismatch.

**Tech Stack:** Python 3.12, standard library JSON/dataclasses, existing BeautifulSoup crawler, unittest.

## Global Constraints

- Tests use offline, license-safe fixtures only.
- URLs, title, price amount, currency, availability, and variant count are exact acceptance fields when supplied by a case.
- This is a quality gate around existing extraction behavior, not a replacement extractor.
- Write and observe a failing test before production code.

---

### Task 1: Add the benchmark contract

**Files:**
- Create: `app/extraction_quality_benchmark.py`
- Create: `test_extraction_quality_benchmark.py`

**Interfaces:**
- `BenchmarkCase`, `BenchmarkReport`, `run_benchmark(cases) -> BenchmarkReport`.
- Report fields: `passed`, `case_results`, `field_pass_rates`.

- [ ] **Step 1: Write a failing test**

```python
report = run_benchmark(sample_cases())
self.assertTrue(report.passed)
self.assertEqual(report.field_pass_rates["price_amount"], 1.0)
```

- [ ] **Step 2: Verify red**

Run `python -m unittest -v test_extraction_quality_benchmark.py`.
Expected: module import failure.

- [ ] **Step 3: Implement the minimal runner**

`run_benchmark` evaluates each case with `product_from_html` or `product_from_shopify_payload`, compares only expected fields, and records expected/actual mismatches.

- [ ] **Step 4: Verify green**

Run `python -m unittest -v test_extraction_quality_benchmark.py`.
Expected: PASS.

### Task 2: Add representative ecommerce coverage and a CLI report

**Files:**
- Modify: `app/extraction_quality_benchmark.py`
- Modify: `test_extraction_quality_benchmark.py`

**Interfaces:**
- `default_cases() -> list[BenchmarkCase]` returns Shopify payload and JSON-LD HTML cases.
- `python -m app.extraction_quality_benchmark` prints JSON and exits 0 only on all-match.

- [ ] **Step 1: Write a failing test**

```python
report = run_benchmark(default_cases())
self.assertEqual(len(report.case_results), 2)
self.assertEqual(report.field_pass_rates["availability"], 1.0)
self.assertEqual(report.field_pass_rates["variant_count"], 1.0)
```

- [ ] **Step 2: Verify red**

Run `python -m unittest -v test_extraction_quality_benchmark.py`.
Expected: missing default fixture pack.

- [ ] **Step 3: Implement the fixtures and entrypoint**

Add a two-variant Shopify payload and a Schema.org JSON-LD product using an `AggregateOffer`. Assert price, stock, currency, and variant count only where source format provides them. Serialize `report.to_dict()` with standard-library JSON.

- [ ] **Step 4: Verify green**

Run `python -m unittest -v test_extraction_quality_benchmark.py` and `python -m app.extraction_quality_benchmark`.
Expected: tests PASS and report contains two all-passing cases.

### Task 3: Run the release quality gate

**Files:**
- No changes expected.

- [ ] **Step 1: Run full backend verification**

Run `python -m unittest discover -v`.
Expected: all tests PASS.

- [ ] **Step 2: Run frontend verification**

From `frontend/`, run `npm.cmd run build` and `npm.cmd run test:ui-contract`.
Expected: both commands exit 0.

- [ ] **Step 3: Run API smoke and benchmark report**

Run `$env:START_BACKGROUND_WORKERS='false'; python -m app.api_smoke` and `python -m app.extraction_quality_benchmark`.
Expected: both commands exit 0.
