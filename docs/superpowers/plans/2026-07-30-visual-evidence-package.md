# Visual Evidence Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist secure, deduplicated before/after page screenshots so a change event can be visually verified.

**Architecture:** Extend the existing Playwright renderer to return PNG bytes. A focused evidence module computes hashes and pixel ratios and writes PNGs under the private data directory. `source_snapshots` stores only metadata and a relative path; the API authorizes snapshot-image reads through site ownership before the React detail page renders the two images.

**Tech Stack:** FastAPI, SQLite/PostgreSQL migrations, Playwright, Pillow, React 19, TypeScript, Vite, Python `unittest`.

## Global Constraints

- Capture only public pages already accepted by the existing SSRF-safe renderer.
- Keep screenshots outside `static/`; return them only from an authenticated owner-checked API route.
- Persist the baseline and changed screenshots, never identical no-change scans.
- Screenshot failures must not fail text snapshots, discovery, or event creation.
- Additive migrations must exist for both SQLite and PostgreSQL.
- Every production behavior is introduced with an offline failing test first.

---

### Task 1: Screenshot primitives and renderer output

**Files:**
- Modify: `requirements.txt`
- Modify: `app/render_worker.py:11-91`
- Create: `app/visual_evidence.py`
- Test: `test_visual_evidence.py`

**Interfaces:**
- Produces `RenderedPage.screenshot_png: bytes | None`.
- Produces `screenshot_hash(png: bytes) -> str` and `visual_change_ratio(before: bytes, after: bytes) -> float`.
- Later tasks consume a `float` in the inclusive range `0.0..1.0`; identical PNG bytes return `0.0` without image decoding.

- [ ] **Step 1: Write the failing tests**

```python
def test_identical_screenshots_have_same_hash_and_zero_ratio():
    png = make_png("#ffffff")
    self.assertEqual(screenshot_hash(png), screenshot_hash(png))
    self.assertEqual(visual_change_ratio(png, png), 0.0)

def test_different_screenshots_report_a_positive_ratio():
    self.assertGreater(visual_change_ratio(make_png("#ffffff"), make_png("#000000")), 0.0)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest test_visual_evidence.py`  
Expected: failure because `app.visual_evidence` and its functions do not exist.

- [ ] **Step 3: Implement the minimal primitives and renderer capture**

```python
# app/visual_evidence.py
def screenshot_hash(png: bytes) -> str:
    return hashlib.sha256(png).hexdigest()

def visual_change_ratio(before: bytes, after: bytes) -> float:
    if before == after:
        return 0.0
    # Pillow opens both images, converts them to RGBA, fits both to the larger size,
    # then divides changed RGBA pixels by all pixels.
```

```python
# app/render_worker.py
@dataclass
class RenderedPage:
    url: str
    html: str
    text: str
    status_code: int | None = None
    screenshot_png: bytes | None = None

# after page content is ready
screenshot_png = await page.screenshot(type="png", full_page=True)
```

Add `Pillow==11.0.0` to `requirements.txt`; return the screenshot bytes with the existing URL, HTML, text, and status fields.

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `python -m unittest test_visual_evidence.py`  
Expected: PASS with both equal and unequal image cases.

- [ ] **Step 5: Commit the task**

```powershell
git add requirements.txt app/render_worker.py app/visual_evidence.py test_visual_evidence.py
git commit -m "feat: capture screenshot bytes and compare visual evidence"
```

### Task 2: Private evidence persistence and snapshot metadata

**Files:**
- Create: `app/evidence_store.py`
- Modify: `app/monitor.py:525-585`
- Modify: `app/db_sqlite_maintenance.py:110-160`
- Create: `app/migrations/sqlite/003_source_snapshot_visual_evidence.sql`
- Create: `app/migrations/postgresql/003_source_snapshot_visual_evidence.sql`
- Test: `test_snapshot_visual_evidence.py`

**Interfaces:**
- Consumes PNG bytes and `source_id`, `snapshot_id`.
- Produces `save_screenshot(source_id: int, snapshot_id: int, png: bytes) -> str`, a relative evidence path.
- Adds nullable snapshot fields `screenshot_hash`, `screenshot_path`, `visual_change_ratio`, and `screenshot_error`.
- `capture_source_snapshot` returns its existing fields plus `screenshot_saved: bool` and `visual_change_ratio: float | None`.

- [ ] **Step 1: Write the failing persistence tests**

```python
async def test_baseline_snapshot_persists_a_private_png(self):
    result = await capture_with_png(source_data, png=make_png("#ffffff"), baseline=True)
    snapshot = load_snapshot(result["snapshot_id"])
    self.assertTrue((EVIDENCE_DIR / snapshot["screenshot_path"]).is_file())
    self.assertTrue(snapshot["screenshot_hash"])

async def test_identical_follow_up_does_not_persist_another_png(self):
    await capture_with_png(source_data, png=make_png("#ffffff"), baseline=True)
    result = await capture_with_png(source_data, png=make_png("#ffffff"), baseline=False)
    self.assertFalse(result["screenshot_saved"])
    self.assertIsNone(load_snapshot(result["snapshot_id"])["screenshot_path"])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest test_snapshot_visual_evidence.py`  
Expected: failure because the evidence schema, store, and snapshot fields do not exist.

- [ ] **Step 3: Implement migrations, store, and capture decision**

```sql
ALTER TABLE source_snapshots ADD COLUMN screenshot_hash TEXT;
ALTER TABLE source_snapshots ADD COLUMN screenshot_path TEXT;
ALTER TABLE source_snapshots ADD COLUMN visual_change_ratio REAL;
ALTER TABLE source_snapshots ADD COLUMN screenshot_error TEXT;
```

```python
# app/evidence_store.py
EVIDENCE_DIR = DATA_DIR / "evidence"

def save_screenshot(source_id: int, snapshot_id: int, png: bytes) -> str:
    relative = Path(f"source-{source_id}") / f"snapshot-{snapshot_id}.png"
    target = EVIDENCE_DIR / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(png)
    return relative.as_posix()
```

In `capture_source_snapshot`, render a PNG independently of whether HTTP text was sufficient. Query the most recent same-source snapshot with a non-null `screenshot_path`; save the new PNG only for a baseline, a changed text hash, a changed screenshot hash, or when no prior PNG exists. Store a short classification such as `render_unavailable` in `screenshot_error` on failure and continue the existing text-diff flow.

- [ ] **Step 4: Run focused tests to verify they pass**

Run: `python -m unittest test_visual_evidence.py test_snapshot_visual_evidence.py test_snapshot_evidence_persistence.py`  
Expected: PASS; verify no PNG is written for the identical follow-up.

- [ ] **Step 5: Commit the task**

```powershell
git add app/evidence_store.py app/monitor.py app/db_sqlite_maintenance.py app/migrations/sqlite/003_source_snapshot_visual_evidence.sql app/migrations/postgresql/003_source_snapshot_visual_evidence.sql test_snapshot_visual_evidence.py
git commit -m "feat: persist changed visual evidence privately"
```

### Task 3: Authorized evidence API

**Files:**
- Modify: `app/main.py:185-191,1006-1060`
- Test: `test_snapshot_screenshot_api.py`

**Interfaces:**
- Extends each `snapshot_detail` response with `screenshot_url: str | None`.
- Produces `GET /api/source-snapshots/{snapshot_id}/screenshot`.
- Uses `CurrentUser`, returning 404 for no snapshot, no saved PNG, a path outside `EVIDENCE_DIR`, or an owner mismatch.

- [ ] **Step 1: Write the failing authorization tests**

```python
def test_owner_can_download_saved_snapshot_png(self):
    response = owner_client.get(f"/api/source-snapshots/{snapshot_id}/screenshot", headers=owner_headers)
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.headers["content-type"], "image/png")

def test_other_user_cannot_download_saved_snapshot_png(self):
    response = stranger_client.get(f"/api/source-snapshots/{snapshot_id}/screenshot", headers=stranger_headers)
    self.assertEqual(response.status_code, 404)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest test_snapshot_screenshot_api.py`  
Expected: failure because the route does not exist.

- [ ] **Step 3: Implement the owner-checked route and detail URL**

```python
@app.get("/api/source-snapshots/{snapshot_id}/screenshot")
async def get_snapshot_screenshot(snapshot_id: int, user: dict = CurrentUser):
    # Join source_snapshots -> monitor_sources -> sites and require sites.user_id = user["id"].
    # Resolve screenshot_path beneath EVIDENCE_DIR and reject any escaped path.
    # Return FileResponse(path, media_type="image/png") only when the file exists.
```

`snapshot_detail` must add the API URL only when the metadata contains a saved screenshot path; never serialize the storage path itself to the browser.

- [ ] **Step 4: Run API and isolation tests to verify they pass**

Run: `python -m unittest test_snapshot_screenshot_api.py && python -m app.api_smoke && python -m app.core_isolation_smoke`  
Expected: PASS; the existing multi-user isolation behavior remains intact.

- [ ] **Step 5: Commit the task**

```powershell
git add app/main.py test_snapshot_screenshot_api.py
git commit -m "feat: serve screenshot evidence to authorized owners"
```

### Task 4: Real visual evidence in the change-detail UI

**Files:**
- Modify: `frontend/src/api/changes.ts:3-20`
- Modify: `frontend/src/features/changes/ChangeDetailPage.tsx:214-420`
- Modify: `frontend/src/styles.css` only if image sizing needs an existing-class adjustment
- Test: `test_change_detail_visual_evidence_ui.py`

**Interfaces:**
- Consumes optional `SourceSnapshot.screenshot_url`, `visual_change_ratio`, and `screenshot_error`.
- Displays `<img>` elements only for owner-authorized API URLs.
- Shows a precise missing-evidence message rather than a fake screenshot placeholder.

- [ ] **Step 1: Write the failing UI contract test**

```python
def test_change_detail_uses_real_snapshot_screenshot_urls():
    page = read_change_detail_page()
    self.assertIn("snapshot_before?.screenshot_url", page)
    self.assertIn("snapshot_after?.screenshot_url", page)
    self.assertIn("screenshot_error", page)
    self.assertNotIn("真实截图服务接入后显示页面快照", page)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest test_change_detail_visual_evidence_ui.py`  
Expected: failure because the page only renders `ScreenshotPlaceholder`.

- [ ] **Step 3: Implement the minimal UI replacement**

```tsx
function ScreenshotEvidence({ snapshot, label }: { snapshot?: SourceSnapshot | null; label: string }) {
  if (snapshot?.screenshot_url) {
    return <img src={snapshot.screenshot_url} alt={label} />;
  }
  return <div className="screenshot-placeholder">{snapshot?.screenshot_error || "未保存重复截图"}</div>;
}
```

Render one component for `snapshot_before` and one for `snapshot_after`; show the stored percentage only when `visual_change_ratio` is non-null. Keep the existing text diff and operation controls unchanged.

- [ ] **Step 4: Run UI tests and production build**

Run: `python -m unittest test_change_detail_evidence_ui.py test_change_detail_visual_evidence_ui.py; npm.cmd run build; npm.cmd run test:ui-contract` from `frontend/`  
Expected: all commands pass and no screenshot placeholder claims the feature is not connected.

- [ ] **Step 5: Commit the task**

```powershell
git add frontend/src/api/changes.ts frontend/src/features/changes/ChangeDetailPage.tsx frontend/src/styles.css test_change_detail_visual_evidence_ui.py
git commit -m "feat: show real screenshot evidence in change details"
```

### Task 5: End-to-end verification and handoff

**Files:**
- Modify: `app/api_smoke.py` only if its event fixture needs screenshots to validate the expanded detail response
- Test: all visual-evidence tests plus existing smoke scripts

**Interfaces:**
- Validates the complete capture-to-owner-view path without real internet access.

- [ ] **Step 1: Add a failing smoke assertion if the detail fixture lacks a `screenshot_url`**

```python
detail = client.get(f"/api/change-events/{event_id}", headers=headers).json()
self.assertIn("screenshot_url", detail["snapshot_after"])
```

- [ ] **Step 2: Run the smoke assertion to verify it fails before any fixture update**

Run: `python -m app.api_smoke`  
Expected: failure only if the API smoke fixture has not created a private PNG.

- [ ] **Step 3: Update the fixture with a deterministic one-pixel PNG and exercise the owner URL**

```python
image = client.get(detail["snapshot_after"]["screenshot_url"], headers=headers)
if image.status_code != 200 or image.headers.get("content-type") != "image/png":
    raise RuntimeError("snapshot screenshot evidence was not retrievable")
```

- [ ] **Step 4: Run the full verification suite and preview manually**

Run:

```powershell
$env:START_BACKGROUND_WORKERS='false'
python -m unittest test_visual_evidence.py test_snapshot_visual_evidence.py test_snapshot_screenshot_api.py test_change_detail_visual_evidence_ui.py test_api_boolean_serialization.py test_source_capture_evidence.py test_snapshot_evidence_persistence.py test_change_detail_evidence_ui.py test_db_boolean_sql.py test_rq_worker_windows.py test_static_advanced_toggle.py test_static_monitor_settings_ui.py
python -m app.api_smoke
python -m app.core_isolation_smoke
python -m app.notification_outbox_smoke
python -m app.notification_outbox_failure_smoke
python -m app.notification_retry_smoke
python -m app.notification_isolation_smoke
```

Then from `frontend/` run `npm.cmd run build` and `npm.cmd run test:ui-contract`, start the local preview, and inspect a real change-detail image pair in the browser.

- [ ] **Step 5: Commit and push the completed feature**

```powershell
git add app/api_smoke.py
git commit -m "test: verify visual evidence end to end"
git push
```
