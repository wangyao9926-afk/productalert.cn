# 首次全站基线扫描与商品库 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** 用户保存官网根域名后立即创建并追踪一次全站商品基线扫描，完成后可查看商品总数、关键字段、官网链接和后续变化。

**Architecture:** 保持 FastAPI + RQ 的异步扫描模式。扫描任务将阶段和计数写入现有 \`scan_jobs.result\` JSON；受鉴权保护的单任务 API 提供轮询数据。React 在创建监控后提交首次扫描，轮询状态并在完成后引导用户进入按站点过滤的商品库。

**Tech Stack:** Python 3.14, FastAPI, PostgreSQL/SQLite compatibility layer, Redis/RQ, React 19, TypeScript, Vite, \`unittest\`.

## Global Constraints

- 首次基线扫描不得发送新品、价格或库存通知。
- 商品发现继续使用现有 sitemap、子 sitemap、页面链接和 Shopify products JSON，并遵守现有 URL 安全与同域限制。
- 扫描状态、商品和证据必须按站点所属用户鉴权。
- 生产使用 PostgreSQL、Redis、RQ 和独立 Worker；API 请求线程不得执行全站抓取。
- 生产前端禁用演示数据，只请求 api.productalert.cn。
- 只使用 \`python -m unittest\` 和 \`npm.cmd run test:ui-contract\`；不引入 pytest。

---

## File Structure

- \`app/monitor.py\`：进度 JSON 写入，以及基线扫描的聚合计数。
- \`app/main.py\`：单任务详情、站点基线摘要和商品 API。
- \`test_baseline_scan_progress.py\`：扫描进度、基线不通知、部分失败和权限测试。
- \`test_baseline_product_api.py\`：站点商品摘要和字段 API 测试。
- \`frontend/src/api/monitors.ts\`：自动首扫和任务详情客户端。
- \`frontend/src/features/monitors/BaselineScanPage.tsx\`：首扫进度页。
- \`frontend/src/features/products/ProductsPage.tsx\`：站点商品数量、卖点、类型和官网跳转。
- \`frontend/src/app/routes.tsx\`：基线页路由。
- \`frontend/scripts/ui-contract-check.mjs\`：首扫和商品库 UI 合约。
- \`docs/NETLIFY_BACKEND_DEPLOYMENT.md\`：生产队列和域名配置。

### Task 1: 提供受鉴权保护的扫描任务进度 API

**Files:**
- Modify: \`app/monitor.py:68-132\`
- Modify: \`app/main.py:1084-1108\`
- Create: \`test_baseline_scan_progress.py\`

**Interfaces:**
- Produces \`update_scan_job_progress(job_id: int, *, phase: str, discovered_count: int, processed_count: int, failed_count: int, product_count: int | None = None, message: str = "") -> None\`.
- Produces \`GET /api/scan-jobs/{job_id}\` with row fields and \`result.progress\`.
- Stores \`result.progress = {phase, discovered_count, processed_count, failed_count, product_count}\`.

- [ ] **Step 1: Write the failing API and ownership tests**

\`\`\`python
def test_owner_can_read_running_baseline_scan_progress(self):
    response = client.get("/api/scan-jobs/" + str(job_id), headers=headers)
    self.assertEqual(response.status_code, 200, response.text)
    self.assertEqual(response.json()["result"]["progress"]["processed_count"], 5)

def test_other_user_cannot_read_baseline_scan_progress(self):
    response = other_client.get("/api/scan-jobs/" + str(job_id), headers=other_headers)
    self.assertEqual(response.status_code, 404, response.text)
\`\`\`

Insert the job with \`status="running"\` and \`json_dumps({"progress": {"phase": "extracting_products", "discovered_count": 12, "processed_count": 5, "failed_count": 1, "product_count": 5}})\`.

- [ ] **Step 2: Run the test to verify it fails**

Run: \`& .\\.venv\\Scripts\\python.exe -m unittest -q test_baseline_scan_progress.BaselineScanProgressApiTests\`

Expected: FAIL with HTTP 404 for the owner request.

- [ ] **Step 3: Implement the smallest compatible API**

\`\`\`python
def update_scan_job_progress(job_id, *, phase, discovered_count, processed_count,
                             failed_count, product_count=None, message=""):
    progress = {"phase": phase, "discovered_count": discovered_count,
                "processed_count": processed_count, "failed_count": failed_count,
                "product_count": product_count}
    with get_db() as db:
        update_by_id(db, "scan_jobs", job_id, {
            "candidates_count": discovered_count, "error_count": failed_count,
            "message": message, "result": json_dumps({"progress": progress}),
        })
\`\`\`

Add \`GET /api/scan-jobs/{job_id}\` that joins \`sites\`, filters \`sites.user_id = user["id"]\`, returns \`row_to_dict(row)\`, and raises HTTP 404 when absent.

- [ ] **Step 4: Verify focused tests**

Run: \`& .\\.venv\\Scripts\\python.exe -m unittest -q test_baseline_scan_progress.BaselineScanProgressApiTests\`

Expected: PASS; owner receives progress and a second user receives 404.

- [ ] **Step 5: Commit**

\`\`\`powershell
git add app/monitor.py app/main.py test_baseline_scan_progress.py
git commit -m "feat: expose baseline scan progress"
\`\`\`

### Task 2: 将首次基线扫描计数写入任务

**Files:**
- Modify: \`app/monitor.py:951-1181\`
- Modify: \`test_baseline_scan_progress.py\`

**Interfaces:**
- Consumes \`update_scan_job_progress\`.
- Produces phases \`discovering\`, \`extracting_products\`, \`completed\`, \`partial_success\`, \`failed\`.
- Produces final \`result.progress.baseline_completed: bool\`.

- [ ] **Step 1: Write the failing baseline semantics test**

\`\`\`python
async def test_first_baseline_records_products_without_new_product_events(self):
    result = await scan_site(site_id, notify=True, trigger_type="baseline", job_id=job_id)
    job = load_scan_job(job_id)
    self.assertEqual(result["checked"], 2)
    self.assertTrue(job["result"]["progress"]["baseline_completed"])
    self.assertEqual(job["result"]["progress"]["product_count"], 2)
    self.assertEqual(fetchall(db, "SELECT * FROM change_events WHERE site_id = ?", (site_id,)), [])
\`\`\`

Patch \`discover_candidates\` to return two candidates and \`extract_candidate_product\` to return two valid extracted products.

- [ ] **Step 2: Run the test to verify it fails**

Run: \`& .\\.venv\\Scripts\\python.exe -m unittest -q test_baseline_scan_progress.BaselineScanProgressRuntimeTests.test_first_baseline_records_products_without_new_product_events\`

Expected: FAIL because \`baseline_completed\` is absent from the job result.

- [ ] **Step 3: Implement progress at discovery and extraction boundaries**

At task start write phase \`discovering\` with zero counts. After \`discover_candidates\`, write \`extracting_products\` with \`discovered_count=len(candidates)\`. After each candidate, increment \`processed_count\`; increment \`failed_count\` only for extraction exceptions; write the current progress. In baseline mode call \`extract_and_store_product\` with \`discovery_status="baseline"\`, \`notify=False\`, \`record_changes=False\`.

At completion, count \`products WHERE site_id = ?\`; write \`baseline_completed=True\` only when the count is positive. Finish as \`success\` when no candidate fails, \`partial_success\` when products exist and one or more candidates fail, otherwise \`failed\`.

- [ ] **Step 4: Verify runtime behavior and event suppression**

Run: \`& .\\.venv\\Scripts\\python.exe -m unittest -q test_baseline_scan_progress.BaselineScanProgressRuntimeTests test_event_suppression\`

Expected: PASS; baseline stores products and emits no change-event notification.

- [ ] **Step 5: Commit**

\`\`\`powershell
git add app/monitor.py test_baseline_scan_progress.py
git commit -m "feat: track first baseline scan progress"
\`\`\`

### Task 3: 增加基线摘要和完整商品库 API 契约

**Files:**
- Modify: \`app/main.py:958-1057\`
- Modify: \`frontend/src/types/api.ts\`
- Create: \`test_baseline_product_api.py\`

**Interfaces:**
- Produces \`GET /api/sites/{site_id}/baseline-summary\` returning \`{site_id, product_count, latest_job, baseline_completed}\`.
- Extends \`Product\` with \`item_type\`, \`features\`, \`description\`, \`image_url\`, \`compare_at_price\`, \`variant_count\`, \`url\`, \`availability\`, and \`currency\`.

- [ ] **Step 1: Write failing count, fields and ownership tests**

\`\`\`python
def test_owner_reads_site_baseline_summary_and_product_fields(self):
    summary = client.get("/api/sites/" + str(site_id) + "/baseline-summary", headers=headers)
    self.assertEqual(summary.status_code, 200, summary.text)
    self.assertEqual(summary.json()["product_count"], 1)
    products = client.get("/api/products?site_id=" + str(site_id), headers=headers).json()
    self.assertEqual(products[0]["item_type"], "product_detail")
    self.assertEqual(products[0]["features"], ["Water resistant"])
    self.assertEqual(products[0]["url"], product_url)
\`\`\`

Add the second-user assertion that the summary response is HTTP 404.

- [ ] **Step 2: Run the failing tests**

Run: \`& .\\.venv\\Scripts\\python.exe -m unittest -q test_baseline_product_api.BaselineProductApiTests\`

Expected: FAIL with HTTP 404 for the new summary route.

- [ ] **Step 3: Implement the summary and explicit product contract**

Add the owner check, a \`COUNT(*)\` query against \`products\`, and the latest \`site_scan\` row query ordered by \`queued_at DESC, id DESC\`. Return exactly:

\`\`\`python
{"site_id": site_id, "product_count": int(count["count"]),
 "latest_job": latest_job,
 "baseline_completed": bool(progress.get("baseline_completed"))}
\`\`\`

Make the existing product list serialize \`features\` through \`row_to_dict\` and return all listed key fields identically for PostgreSQL JSONB and SQLite JSON.

- [ ] **Step 4: Verify API and compatibility tests**

Run: \`& .\\.venv\\Scripts\\python.exe -m unittest -q test_baseline_product_api test_price_matrix test_variant_monitoring\`

Expected: PASS; fields are JSON-compatible and unauthorized users receive 404.

- [ ] **Step 5: Commit**

\`\`\`powershell
git add app/main.py frontend/src/types/api.ts test_baseline_product_api.py
git commit -m "feat: expose baseline product summary"
\`\`\`

### Task 4: 创建监控后自动启动首扫并显示进度页

**Files:**
- Modify: \`frontend/src/api/monitors.ts\`
- Modify: \`frontend/src/features/monitors/CreateMonitorPage.tsx\`
- Create: \`frontend/src/features/monitors/BaselineScanPage.tsx\`
- Modify: \`frontend/src/app/routes.tsx\`
- Modify: \`frontend/scripts/ui-contract-check.mjs\`

**Interfaces:**
- Produces \`createMonitorAndStartBaseline(input): Promise<{site: Site; job: ScanJob}>\`.
- Produces \`getScanJob(jobId: number): Promise<ScanJob>\`.
- Produces route \`/monitors/:siteId/baseline/:jobId\`.
- Consumes Task 1 and Task 3 APIs.

- [ ] **Step 1: Add failing UI contract assertions**

\`\`\`js
assert.match(createMonitorPage, /createMonitorAndStartBaseline/);
assert.match(baselineScanPage, /setInterval/);
assert.match(baselineScanPage, /已发现/);
assert.match(baselineScanPage, /已处理/);
assert.match(baselineScanPage, /查看商品库/);
\`\`\`

- [ ] **Step 2: Run the UI contract check**

Run: \`npm.cmd run test:ui-contract\`

Expected: FAIL because the client method and \`BaselineScanPage.tsx\` do not exist.

- [ ] **Step 3: Implement the client workflow**

\`\`\`ts
export async function createMonitorAndStartBaseline(input: CreateMonitorTaskInput) {
  const { site } = await createMonitorTask(input);
  const job = await triggerSiteScan(site.id);
  return { site, job };
}
export function getScanJob(jobId: number) {
  return getJson<ScanJob>("/api/scan-jobs/" + jobId);
}
\`\`\`

Modify \`CreateMonitorPage\` to call this method, then navigate to the baseline route. Do not create a second source: \`POST /api/sites\` already creates the homepage source, so obtain that source from the returned site or \`GET /api/sites\` before scanning.

Implement \`BaselineScanPage\` with a 2-second polling interval and cleanup. It must display queued/running/final state, discovered, processed, failed, product count, current message, a retry button for terminal failure, and a “查看商品库” link filtered to the current site after terminal success.

- [ ] **Step 4: Verify frontend contract and build**

Run: \`npm.cmd run test:ui-contract; npm.cmd run build\`

Expected: PASS; the Vite bundle contains the new route.

- [ ] **Step 5: Commit**

\`\`\`powershell
git add frontend/src/api/monitors.ts frontend/src/features/monitors/CreateMonitorPage.tsx frontend/src/features/monitors/BaselineScanPage.tsx frontend/src/app/routes.tsx frontend/scripts/ui-contract-check.mjs
git commit -m "feat: start and display first baseline scan"
\`\`\`

### Task 5: 商品库展示基线字段和官网跳转

**Files:**
- Modify: \`frontend/src/api/products.ts\`
- Modify: \`frontend/src/features/products/ProductsPage.tsx\`
- Modify: \`frontend/scripts/ui-contract-check.mjs\`

**Interfaces:**
- Consumes the summary endpoint and site-filtered products endpoint.
- Produces a site-filtered product page with product-count headline, type, feature summary and official URL link.

- [ ] **Step 1: Add failing product-library UI assertions**

\`\`\`js
assert.match(productsPage, /URLSearchParams/);
assert.match(productsPage, /baseline-summary/);
assert.match(productsPage, /产品总数/);
assert.match(productsPage, /卖点/);
assert.match(productsPage, /商品类型/);
assert.match(productsPage, /target="_blank"/);
\`\`\`

- [ ] **Step 2: Run the UI contract check**

Run: \`npm.cmd run test:ui-contract\`

Expected: FAIL because the page does not parse \`site_id\` or render baseline-summary fields.

- [ ] **Step 3: Implement the site-scoped product library**

Parse \`site_id\` through \`new URLSearchParams(location.search)\`. When a site is selected, load both the baseline summary and \`GET /api/products?site_id=<id>\`. Render a selected-site card with product count, baseline-completed state and latest-job status. Add columns for \`item_type\` and \`features.slice(0, 3).join(" · ")\`; retain \`target="_blank" rel="noreferrer"\` for the official URL. If a baseline is active, render its progress instead of an apparently final zero-product state.

- [ ] **Step 4: Verify frontend contract and build**

Run: \`npm.cmd run test:ui-contract; npm.cmd run build\`

Expected: PASS with no TypeScript errors.

- [ ] **Step 5: Commit**

\`\`\`powershell
git add frontend/src/api/products.ts frontend/src/features/products/ProductsPage.tsx frontend/scripts/ui-contract-check.mjs
git commit -m "feat: show baseline product library details"
\`\`\`

### Task 6: 配置生产队列并验证真实扫描闭环

**Files:**
- Modify: \`docs/NETLIFY_BACKEND_DEPLOYMENT.md\`
- Modify: \`app/api_smoke.py\`

**Interfaces:**
- Produces a Railway web service, PostgreSQL, Redis and a separate worker using \`python -m app.rq_worker\`.
- Produces production API base URL \`https://api.productalert.cn\`.

- [ ] **Step 1: Add failing production-readiness assertions to the API smoke script**

\`\`\`python
health = client.get("/api/system/health", headers=headers).json()
if health["database_backend"] != "postgresql":
    raise RuntimeError("production backend must use PostgreSQL")
if health["queue_backend"] != "rq" or not health["redis_configured"]:
    raise RuntimeError("production backend must use Redis/RQ")
\`\`\`

- [ ] **Step 2: Run the smoke script**

Run: \`& .\\.venv\\Scripts\\python.exe -m app.api_smoke\`

Expected: PASS with the local PostgreSQL/Redis profile; otherwise FAIL with the readiness message.

- [ ] **Step 3: Add exact Railway and Netlify configuration instructions**

Document: a Railway Postgres service is referenced by \`DATABASE_URL\`; a Railway Redis service is referenced by \`REDIS_URL\`; queue backend is \`rq\`; the web process runs Uvicorn using Railway’s injected port; the worker process runs \`python -m app.rq_worker\`; the frontend API base is \`https://api.productalert.cn\`; demo fallback is false; CORS origins are the root and www productalert domains; cookies are secure with SameSite none.

- [ ] **Step 4: Verify local suites, production health and one permitted baseline scan**

Run:

\`\`\`powershell
& .\\.venv\\Scripts\\python.exe -m unittest discover -q
Set-Location frontend; npm.cmd run test:ui-contract; npm.cmd run build
Invoke-WebRequest -UseBasicParsing https://api.productalert.cn/api/system/ping
\`\`\`

Expected: local suites PASS; ping returns HTTP 200 and \`{"ok":true}\`. In the deployed UI, create one permitted public monitoring task and verify progress reaches a product count without a new-product notification.

- [ ] **Step 5: Commit**

\`\`\`powershell
git add docs/NETLIFY_BACKEND_DEPLOYMENT.md app/api_smoke.py
git commit -m "docs: configure production baseline scanning"
\`\`\`

