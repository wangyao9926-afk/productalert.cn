# Change Detail Diff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `/changes/:id` frontend detail page that explains why a detected change was flagged.

**Architecture:** Add a focused React page under `frontend/src/features/changes/` using existing overview/demo data plus local mock diff details. Route both `/changes/:id` and existing inbox/overview detail actions into it. Extend the UI contract script to lock required audit and diff copy.

**Tech Stack:** React, TypeScript, React Router, Vite, existing CSS variables and layout styles.

## Global Constraints

- Follow `docs/PRODUCT_ROADMAP.md` Phase 5 only.
- Do not add new dependencies.
- Use mock/local diff data before real snapshot integration.
- Keep the macOS-style console direction.
- Verify with `npm.cmd run test:ui-contract`, `npm.cmd run build`, and HTTP 200 on `/changes/1`.

---

### Task 1: Contract Test for Change Detail

**Files:**
- Modify: `frontend/scripts/ui-contract-check.mjs`

**Interfaces:**
- Consumes: existing source file scanner.
- Produces: contract assertions for `src/features/changes/ChangeDetailPage.tsx` and `/changes/:id`.

- [ ] Add `src/features/changes/ChangeDetailPage.tsx` to the scanned source files.
- [ ] Assert `routes.tsx` renders `ChangeDetailPage`.
- [ ] Assert required page text: `变化详情`, `字段差异`, `价格差异`, `截图对比`, `文本 Diff`, `置信度`, `严重程度`, `扫描元数据`, `处理记录`, `标记误报`.
- [ ] Run `npm.cmd run test:ui-contract`; expected failure before implementation because the page file does not exist.

### Task 2: Change Detail Page and Route

**Files:**
- Create: `frontend/src/features/changes/ChangeDetailPage.tsx`
- Modify: `frontend/src/app/routes.tsx`
- Modify: `frontend/src/features/inbox/InboxPage.tsx`

**Interfaces:**
- Consumes: `loadOverview()` and `useParams()`.
- Produces: `/changes/:id` route and detail links from inbox rows.

- [ ] Implement `ChangeDetailPage` with event lookup by route id and fallback to the first demo event.
- [ ] Show summary header, confidence, severity, scan metadata, old/new field comparison, price delta, screenshot comparison placeholders, text diff, and processing history.
- [ ] Add buttons for `标记已处理` and `标记误报` as local state actions.
- [ ] Route `/changes/:id` to `ChangeDetailPage`.
- [ ] Link inbox row detail button to `/changes/{id}`.

### Task 3: Change Detail Styles

**Files:**
- Modify: `frontend/src/styles/global.css`

**Interfaces:**
- Consumes: existing `.panel`, `.page-header`, `.tag`, `.metric-card`, `.primary-button`.
- Produces: responsive styles for diff grids, field comparison, screenshot placeholders, and timeline.

- [ ] Add page layout, confidence cards, field diff table, visual comparison panels, text diff blocks, metadata, and timeline styles.
- [ ] Keep mobile behavior scannable without horizontal overflow.

### Task 4: Verification

**Files:**
- No source changes unless verification reveals a defect.

- [ ] Run `npm.cmd run test:ui-contract`; expected pass.
- [ ] Run `npm.cmd run build`; expected pass.
- [ ] Run `powershell -ExecutionPolicy Bypass -File .\start-frontend-preview.ps1`; expected stable preview.
- [ ] Request `http://127.0.0.1:4173/changes/1`; expected HTTP 200.
