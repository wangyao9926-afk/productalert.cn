# Create Monitor Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `/monitors/new` frontend wizard for creating a mock monitor task.

**Architecture:** Add a focused React page under `frontend/src/features/monitors/`, route `/monitors/new` to it, and extend the existing UI contract script so the wizard remains navigable and free of mojibake. The page uses local state only and does not introduce backend writes.

**Tech Stack:** React, TypeScript, React Router, Vite, existing CSS variables and layout styles.

## Global Constraints

- Follow `docs/PRODUCT_ROADMAP.md` Phase 3 only.
- Do not add new dependencies.
- Keep the macOS-style console direction.
- Use mock/local state before real backend integration.
- Verify with `npm.cmd run test:ui-contract` and `npm.cmd run build`.

---

### Task 1: Contract Test for Wizard

**Files:**
- Modify: `frontend/scripts/ui-contract-check.mjs`

**Interfaces:**
- Consumes: existing source file scanner.
- Produces: contract assertions for `src/features/monitors/CreateMonitorPage.tsx` and `/monitors/new`.

- [ ] Add `src/features/monitors/CreateMonitorPage.tsx` to the scanned source files.
- [ ] Assert `routes.tsx` imports and renders `CreateMonitorPage`.
- [ ] Assert the wizard source includes `新建监控`, `目标 URL`, `新品上新`, `价格变化`, `库存变化`, `自动识别`, `CSS 选择器`, `高级规则`, `监控频率`, `通知渠道`, and `保存监控`.
- [ ] Run `npm.cmd run test:ui-contract`; expected failure before implementation because `CreateMonitorPage.tsx` does not exist.

### Task 2: Wizard Page and Route

**Files:**
- Create: `frontend/src/features/monitors/CreateMonitorPage.tsx`
- Modify: `frontend/src/app/routes.tsx`

**Interfaces:**
- Consumes: React Router `Link`.
- Produces: route `/monitors/new` rendering `CreateMonitorPage`.

- [ ] Implement local wizard state for target URL, monitor targets, extraction method, frequency, notifications, and saved draft status.
- [ ] Render four configuration sections matching roadmap Phase 3.
- [ ] Add a review panel that summarizes the configured task.
- [ ] Route `/monitors/new` to `CreateMonitorPage`.

### Task 3: Wizard Styles

**Files:**
- Modify: `frontend/src/styles/global.css`

**Interfaces:**
- Consumes: existing `.panel`, `.button`, `.primary-button`, `.page-header`, and token variables.
- Produces: responsive styles for the wizard page.

- [ ] Add wizard layout, step rail, selectable cards, segmented extraction method, frequency grid, notification checklist, and draft confirmation styles.
- [ ] Keep mobile behavior scannable without horizontal overflow.

### Task 4: Verification

**Files:**
- No source changes unless verification reveals a defect.

- [ ] Run `npm.cmd run test:ui-contract`; expected pass.
- [ ] Run `npm.cmd run build`; expected pass.
- [ ] Run `powershell -ExecutionPolicy Bypass -File .\start-frontend-preview.ps1`; expected stable preview.
- [ ] Request `http://127.0.0.1:4173/monitors/new`; expected HTTP 200.
