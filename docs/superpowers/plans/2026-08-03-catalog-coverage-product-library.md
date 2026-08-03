# 全量商品目录与产品库展示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让公开独立站的商品基线以可解释的质量状态建立，并在产品库中显示带缩略图、类型和卖点的商品档案。

**Architecture:** 把商品发现、单商品读取结果和基线质量统计分开保存。抓取器产生带 HTTP 状态与错误分类的结果，扫描层据此计算可信/不完整基线；前端只消费 API 中的结构化质量字段。对于限流站点，系统遵循站点冷却时间并提供恢复入口，不规避访问限制。

**Tech Stack:** Python 3.14、FastAPI、SQLite/PostgreSQL 兼容迁移、httpx、BeautifulSoup、React 19、TypeScript、Vite、unittest。

## Global Constraints

- 仅监控公开可访问页面；不得用代理、伪造身份或绕过网站访问限制。
- 首次基线不得产生新品、价格或库存通知。
- 429、403、超时、非商品页与解析失败必须分别计数并对用户可见。
- 有未验证可售商品候选时不得把 `baseline_completed` 标为 `true`。
- 产品缩略图使用现有 `image_url`，失败时本地降级，不把外部图片写入数据库。
- 所有站点、任务、候选与商品读取均须保持现有所有者鉴权。
- 后端测试仅使用 `python -m unittest`；前端验证使用 `npm.cmd run test:ui-contract` 和 `npm.cmd run build`。

---

## File Structure

- `app/crawler.py`：结构化 HTTP 读取结果、429 冷却、产品来源发现。
- `app/monitor.py`：候选持久化、扫描质量计数、基线状态与恢复处理。
- `app/task_queue.py`：恢复任务的入队辅助，不重复处理已验证商品。
- `app/main.py`：任务质量、基线摘要与恢复 API。
- `app/migrations/sqlite/004_scan_job_candidates.sql`：SQLite 候选与质量状态迁移。
- `app/migrations/postgresql/004_scan_job_candidates.sql`：PostgreSQL 等价迁移。
- `test_catalog_scan_quality.py`：发现、限流、不完整基线及恢复的后端测试。
- `test_catalog_quality_api.py`：质量摘要与恢复 API 的鉴权测试。
- `frontend/src/api/monitors.ts`：质量状态和恢复任务客户端。
- `frontend/src/features/monitors/BaselineScanPage.tsx`：扫描质量卡片、恢复入口。
- `frontend/src/features/products/ProductsPage.tsx`：站点筛选、缩略图、类型与卖点展示。
- `frontend/src/styles/global.css`：白底缩略图、卖点标签和窄屏布局。
- `frontend/scripts/ui-contract-check.mjs`：产品库和不完整基线 UI 合约。

### Task 1: 保留可解释的商品读取结果与候选清单

**Files:**
- Modify: `app/crawler.py`
- Modify: `app/monitor.py`
- Create: `app/migrations/sqlite/004_scan_job_candidates.sql`
- Create: `app/migrations/postgresql/004_scan_job_candidates.sql`
- Create: `test_catalog_scan_quality.py`

**Interfaces:**
- Produces `FetchResult(url: str, status_code: int | None, content: str | None, error_category: str | None, retry_after_seconds: int | None)`.
- Produces `discover_product_candidates(...) -> list[ProductCandidate]` containing only canonical product candidates.
- Produces `record_scan_candidate(job_id: int, candidate: ProductCandidate, *, status: str, error_category: str | None = None, http_status: int | None = None) -> None`.

- [ ] **Step 1: Write failing crawler quality tests**

```python
def test_product_discovery_excludes_non_product_sitemap_urls(self):
    candidates = discover_product_candidates(
        "https://store.example.com/",
        sitemap_documents={
            "https://store.example.com/sitemap.xml": """
                <urlset>
                  <url><loc>https://store.example.com/products/pump</loc></url>
                  <url><loc>https://store.example.com/blogs/news</loc></url>
                  <url><loc>https://store.example.com/collections/pumps</loc></url>
                </urlset>
            """,
        },
    )
    self.assertEqual([candidate.url for candidate in candidates], ["https://store.example.com/products/pump"])

def test_fetch_result_records_retry_after_for_rate_limit(self):
    result = fetch_result_from_response(
        "https://store.example.com/products/pump",
        status_code=429,
        headers={"Retry-After": "17"},
        content="Too many requests",
    )
    self.assertEqual(result.error_category, "rate_limited")
    self.assertEqual(result.retry_after_seconds, 17)
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `& .\.venv\Scripts\python.exe -m unittest -q test_catalog_scan_quality.CatalogDiscoveryTests`

Expected: FAIL because `discover_product_candidates` and `fetch_result_from_response` do not exist.

- [ ] **Step 3: Add both database migrations**

Create `scan_job_candidates` with `job_id`, `site_id`, `source_id`, `url`, `canonical_key`, `status`, `http_status`, `error_category`, `retry_after_seconds`, `attempt_count`, `payload_json`, `created_at`, and `updated_at`. Add a unique constraint on `(job_id, canonical_key)` and indexes on `(job_id, status)` and `(site_id, status)`. Use SQLite `INTEGER`/`TEXT` and PostgreSQL `BIGINT`/`JSONB` equivalents.

- [ ] **Step 4: Implement the minimum crawler contract**

```python
@dataclass(frozen=True)
class FetchResult:
    url: str
    status_code: int | None
    content: str | None
    error_category: str | None
    retry_after_seconds: int | None

def fetch_result_from_response(url, *, status_code, headers, content):
    if status_code == 429:
        retry_after = int(headers["Retry-After"]) if headers.get("Retry-After", "").isdigit() else None
        return FetchResult(url, status_code, None, "rate_limited", retry_after)
    if status_code >= 400:
        return FetchResult(url, status_code, None, "blocked" if status_code == 403 else "http_error", None)
    return FetchResult(url, status_code, content, None, None)
```

Refactor sitemap and Shopify discovery so only `classify_product_url(url)[0] == "product_detail"` candidates contribute to product discovery count. Preserve collection/page URLs only as inputs for subsequent discovery, not as product candidates.

- [ ] **Step 5: Persist candidate state while scanning**

Before extraction, insert each canonical candidate as `pending`. Store `stored`, `non_product`, `fetch_failed`, `rate_limited`, `blocked`, or `parse_failed` after its outcome. Store Shopify payload JSON only when a candidate came from the public Shopify endpoint. Do not overwrite a successful candidate with a later failure.

- [ ] **Step 6: Verify focused tests and commit**

Run: `& .\.venv\Scripts\python.exe -m unittest -q test_catalog_scan_quality.CatalogDiscoveryTests`

Expected: PASS; product-only counts and `Retry-After` are asserted.

```powershell
git add app/crawler.py app/monitor.py app/migrations/sqlite/004_scan_job_candidates.sql app/migrations/postgresql/004_scan_job_candidates.sql test_catalog_scan_quality.py
git commit -m "feat: record catalog scan candidate quality"
```

### Task 2: 让限流基线保持不完整并支持继续扫描

**Files:**
- Modify: `app/crawler.py`
- Modify: `app/monitor.py`
- Modify: `app/task_queue.py`
- Modify: `app/main.py`
- Modify: `test_catalog_scan_quality.py`
- Create: `test_catalog_quality_api.py`

**Interfaces:**
- Produces `progress.quality = {discovered_product_count, attempted_product_count, stored_product_count, rate_limited_count, blocked_count, fetch_failed_count, parse_failed_count, non_product_count, pending_retry_count, baseline_state}`.
- Produces `resume_scan_job(job_id: int) -> dict`.
- Produces `POST /api/scan-jobs/{job_id}/resume` returning the replacement queued job.

- [ ] **Step 1: Write failing incomplete-baseline and resume tests**

```python
def test_rate_limited_candidates_leave_baseline_incomplete(self):
    result = asyncio.run(scan_site(site_id, trigger_type="baseline", job_id=job_id))
    self.assertEqual(result["progress"]["quality"]["stored_product_count"], 1)
    self.assertEqual(result["progress"]["quality"]["rate_limited_count"], 2)
    self.assertEqual(result["progress"]["quality"]["baseline_state"], "incomplete")
    self.assertFalse(result["progress"]["baseline_completed"])
    self.assertEqual(load_scan_job(job_id)["status"], "partial_success")

def test_owner_can_resume_incomplete_baseline(self):
    response = client.post(f"/api/scan-jobs/{incomplete_job_id}/resume", headers=owner_headers)
    self.assertEqual(response.status_code, 200, response.text)
    self.assertEqual(response.json()["status"], "queued")
    self.assertEqual(response.json()["resume_of_job_id"], incomplete_job_id)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `& .\.venv\Scripts\python.exe -m unittest -q test_catalog_scan_quality.CatalogBaselineQualityTests test_catalog_quality_api.CatalogQualityApiTests`

Expected: FAIL because `quality` and the resume endpoint are absent.

- [ ] **Step 3: Implement adaptive domain cooldown**

Maintain a per-process mapping from canonical domain to `cooldown_until`. When a `FetchResult.error_category == "rate_limited"`, use `retry_after_seconds` when supplied; otherwise use 30 seconds for the first rate limit and double up to 5 minutes for consecutive rate limits. Stop submitting new candidate requests while the domain is cooling down; mark remaining unattempted candidates as `pending_retry`. This only slows or pauses collection and never attempts to bypass access controls.

- [ ] **Step 4: Implement quality-driven baseline completion**

Calculate the quality counters from `scan_job_candidates`. Set `baseline_completed` only when `stored_product_count > 0` and `pending_retry_count + rate_limited_count + blocked_count + fetch_failed_count == 0`. If stored products exist but any of those counters is nonzero, finish as `partial_success` with `baseline_state="incomplete"`. Persist the same quality object inside `scan_jobs.result.progress` and expose it in the site summary.

- [ ] **Step 5: Implement owner-scoped resume**

`resume_scan_job` must verify that the source site still belongs to the caller and that the original job is an incomplete site scan. It creates a new site-scan job with `trigger_type="resume"`, copies only prior `rate_limited`, `fetch_failed`, `blocked`, and `pending_retry` candidates, and enqueues it. It must not clear or reclassify existing `stored` candidates and must use `notify=False` for the resumed baseline.

- [ ] **Step 6: Verify focused tests and commit**

Run: `& .\.venv\Scripts\python.exe -m unittest -q test_catalog_scan_quality.CatalogBaselineQualityTests test_catalog_quality_api.CatalogQualityApiTests`

Expected: PASS; a rate-limited scan is partial/incomplete and only the owner can create a resume job.

```powershell
git add app/crawler.py app/monitor.py app/task_queue.py app/main.py test_catalog_scan_quality.py test_catalog_quality_api.py
git commit -m "feat: expose incomplete catalog scan recovery"
```

### Task 3: 在扫描页显示目录质量与恢复入口

**Files:**
- Modify: `frontend/src/api/monitors.ts`
- Modify: `frontend/src/features/monitors/BaselineScanPage.tsx`
- Modify: `frontend/src/styles/global.css`
- Modify: `frontend/scripts/ui-contract-check.mjs`

**Interfaces:**
- Consumes `ScanJob.result.progress.quality`.
- Produces `resumeScanJob(jobId: number): Promise<ScanJob>`.

- [ ] **Step 1: Add failing UI contract assertions**

```js
assert.match(baselineScanPage, /待验证商品/);
assert.match(baselineScanPage, /受限流/);
assert.match(baselineScanPage, /继续扫描/);
assert.match(monitorsApi, /resumeScanJob/);
```

- [ ] **Step 2: Run the UI contract to verify it fails**

Run: `npm.cmd run test:ui-contract`

Expected: FAIL because the quality labels and resume client do not exist.

- [ ] **Step 3: Implement quality summary and recovery action**

Add TypeScript types for `ScanQuality` and `ScanProgress`. On completed scans, render four explicit quantities: 已验证入库, 待验证商品, 受限流, 读取/解析失败. When `baseline_state === "incomplete"`, render a warning explaining that the displayed product total is not the complete site catalog, plus a `继续扫描` button. Disable it while the resume request is pending; after success, replace the route job id and restart polling.

- [ ] **Step 4: Verify frontend contract and build**

Run: `npm.cmd run test:ui-contract; npm.cmd run build`

Expected: PASS with no TypeScript errors.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/api/monitors.ts frontend/src/features/monitors/BaselineScanPage.tsx frontend/src/styles/global.css frontend/scripts/ui-contract-check.mjs
git commit -m "feat: show catalog scan quality and recovery"
```

### Task 4: 升级产品库为带缩略图与卖点的站点商品档案

**Files:**
- Modify: `frontend/src/features/products/ProductsPage.tsx`
- Modify: `frontend/src/styles/global.css`
- Modify: `frontend/scripts/ui-contract-check.mjs`

**Interfaces:**
- Consumes existing `Product.image_url`, `Product.features`, `Product.description`, `Product.item_type`, and `Product.url`.
- Consumes `site_id` URL query parameter and baseline summary API.

- [ ] **Step 1: Add failing product-library UI contract assertions**

```js
assert.match(productsPage, /URLSearchParams/);
assert.match(productsPage, /product-thumb/);
assert.match(productsPage, /onError/);
assert.match(productsPage, /features\.slice\(0, 2\)/);
assert.match(productsPage, /产品类型/);
```

- [ ] **Step 2: Run the UI contract to verify it fails**

Run: `npm.cmd run test:ui-contract`

Expected: FAIL because the table does not contain thumbnail fallback, site-query parsing, feature tags, or a type label.

- [ ] **Step 3: Implement product row presentation**

Parse `site_id` with `new URLSearchParams(location.search)` and only show products from that site when supplied. In the first table cell render a 56×56 `.product-thumb` white container. Render `<img src={product.image_url}>` with `object-fit: contain`; set local image error state from `onError` and replace the image with a title-initial fallback. Render a deterministic display label from `item_type` and two `features.slice(0, 2)` tags. When no features exist, render the first 90 characters of `description` as the summary.

- [ ] **Step 4: Implement responsive visual rules**

Keep product image tiles white with a subtle border; constrain title/summary to prevent row-height explosions. On narrow layouts keep thumbnail, title, price and external link visible while allowing secondary columns to scroll horizontally. Do not remove current product detail or original-site link actions.

- [ ] **Step 5: Verify frontend contract and build**

Run: `npm.cmd run test:ui-contract; npm.cmd run build`

Expected: PASS with thumbnail fallback and feature contracts present.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/features/products/ProductsPage.tsx frontend/src/styles/global.css frontend/scripts/ui-contract-check.mjs
git commit -m "feat: enrich product library cards"
```

### Task 5: 全量回归与 Flextail 质量验证

**Files:**
- Modify: `docs/QA.md`

**Interfaces:**
- Documents the permitted manual acceptance protocol for public sites that rate-limit requests.

- [ ] **Step 1: Document the acceptance protocol**

Add a section that requires recording the discovered product count, stored product count, status buckets, baseline state, and a comparison against a public platform product count when that endpoint is accessible. A 429 result is accepted only when the baseline is `incomplete` and the UI exposes the recovery action.

- [ ] **Step 2: Run all backend tests**

Run: `& .\.venv\Scripts\python.exe -m unittest discover -q`

Expected: PASS.

- [ ] **Step 3: Run all frontend checks**

Run: `Set-Location frontend; npm.cmd run test:ui-contract; npm.cmd run build`

Expected: PASS.

- [ ] **Step 4: Run the permitted local Flextail acceptance scan**

Start the local backend with the existing development database and in-process worker. Create or resume only the existing Flextail task, then inspect `GET /api/scan-jobs/{job_id}`. Verify either a complete baseline backed by public platform/catalog data or `partial_success` with a nonzero limiting/failure counter. Do not claim the product count is complete when there are pending candidates.

- [ ] **Step 5: Commit**

```powershell
git add docs/QA.md
git commit -m "docs: add catalog scan quality acceptance"
```

## Plan Self-Review

- Spec coverage: Tasks 1–2 implement product-only discovery, rate-limit classification, persistent candidate states, quality threshold and recovery; Task 3 exposes those results; Task 4 implements white-background thumbnails and product selling-point fields; Task 5 verifies the real-site behavior.
- Placeholder scan: no TBD/TODO or deferred implementation markers appear in task steps.
- Type consistency: `ScanQuality` is produced under `ScanJob.result.progress.quality`, used by `BaselineScanPage`, and its data is returned by the existing job-detail API; resume always returns a new `ScanJob`.

## Execution Handoff

This worktree already isolates the feature branch. Execution will proceed inline because the task sequence shares crawler, migration, API, and UI state and requires a live quality verification after each layer.
