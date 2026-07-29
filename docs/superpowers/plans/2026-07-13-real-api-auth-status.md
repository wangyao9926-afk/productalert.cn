# Real API Auth Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the frontend explicitly distinguish real API data from demo fallback data and provide a login/register entry for authenticated backend access.

**Architecture:** Extend the typed frontend API client with status-aware errors, add a small auth API module, add `/login`, and surface data source state in the top bar and overview health strip. Keep all existing demo fallback behavior so the app remains usable when the backend is down or unauthenticated.

**Tech Stack:** React, TypeScript, React Router, Vite, existing FastAPI auth endpoints, existing CSS variables.

## Global Constraints

- Follow `docs/PRODUCT_ROADMAP.md` Phase 6 only.
- Do not add dependencies.
- Do not remove demo fallback.
- Do not require a backend to be running for the frontend to build.
- Verify with `npm.cmd run test:ui-contract`, `npm.cmd run build`, backend smoke when available, and HTTP 200 on `/login`.

---

### Task 1: Contract Test for API Status and Login

**Files:**
- Modify: `frontend/scripts/ui-contract-check.mjs`

**Interfaces:**
- Consumes: current source scanner.
- Produces: checks for `src/api/auth.ts`, `src/features/auth/LoginPage.tsx`, `/login`, and visible data-source copy.

- [ ] Add `src/api/auth.ts` and `src/features/auth/LoginPage.tsx` to scanned source files.
- [ ] Assert `routes.tsx` exposes `/login` and renders `LoginPage`.
- [ ] Assert required login text: `登录 ProductAlert`, `注册新账号`, `邮箱`, `密码`, `进入工作台`.
- [ ] Assert overview contains `真实 API`, `演示数据`, `需要登录`, and `API 不可用`.
- [ ] Run `npm.cmd run test:ui-contract`; expected failure before implementation because auth files do not exist.

### Task 2: Status-Aware API Client

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/api/overview.ts`

**Interfaces:**
- Produces: `ApiError`, `getJson<T>()`, `OverviewMode`, `OverviewData.mode`, and `OverviewData.message`.

- [ ] Add `ApiError` with `status` and `body`.
- [ ] Make `getJson` throw `ApiError` for non-2xx responses.
- [ ] Extend `OverviewData` with `mode: "live" | "demo"`, `reason: "live" | "auth_required" | "api_unavailable" | "api_error"`, and `message`.
- [ ] Keep existing `live` boolean for pages already using it.
- [ ] Map 401 to `auth_required`, network failures to `api_unavailable`, and other responses to `api_error`.

### Task 3: Auth API and Login Page

**Files:**
- Create: `frontend/src/api/auth.ts`
- Create: `frontend/src/features/auth/LoginPage.tsx`
- Modify: `frontend/src/app/routes.tsx`
- Modify: `frontend/src/styles/global.css`

**Interfaces:**
- Consumes: `/api/auth/login`, `/api/auth/register`, `/api/auth/me`, `/api/auth/logout`.
- Produces: login/register page with local loading and error state.

- [ ] Implement `login`, `register`, `getCurrentUser`, and `logout`.
- [ ] Implement `/login` page with login/register mode toggle.
- [ ] Use credentials cookies through existing `getJson`/`fetch` behavior.
- [ ] Add button to return to `/overview` after successful auth.
- [ ] Style the page in the current console aesthetic.

### Task 4: Data Source UI

**Files:**
- Modify: `frontend/src/components/layout/TopBar.tsx`
- Modify: `frontend/src/features/overview/OverviewPage.tsx`
- Modify: `frontend/src/styles/global.css`

**Interfaces:**
- Consumes: `OverviewData.mode`, `reason`, and `message`.
- Produces: visible API state in the overview health strip and a login entry in the top bar.

- [ ] Add a top-bar link to `/login`.
- [ ] Update overview health strip to show `真实 API`, `演示数据`, `需要登录`, or `API 不可用`.
- [ ] Preserve existing summary cards and page behavior.

### Task 5: Verification

**Files:**
- No source changes unless verification reveals a defect.

- [ ] Run `npm.cmd run test:ui-contract`; expected pass.
- [ ] Run `npm.cmd run build`; expected pass.
- [ ] Run `python -m app.api_smoke` if the local Python environment is available; record pass/fail.
- [ ] Run `powershell -ExecutionPolicy Bypass -File .\start-frontend-preview.ps1`; expected stable preview.
- [ ] Request `http://127.0.0.1:4173/login`; expected HTTP 200.
