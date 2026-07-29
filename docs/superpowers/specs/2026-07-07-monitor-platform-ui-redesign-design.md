# Monitor Platform UI Redesign Design

## Goal

第一阶段只做 UI/UX 改造：把当前新品监控工具升级为正式上线可用的 macOS 控制台风格 B 端数据监控工作台。此阶段不修改抓取核心算法、不改认证模型、不改 RQ 调度模型；这些进入后续功能补全和安全加固阶段。

## Current Context

当前项目是 FastAPI + PostgreSQL/SQLite + Redis/RQ + vanilla HTML/CSS/JS。前端主要文件为：

- `static/index.html`
- `static/styles.css`
- `static/app.js`

已有页面包括：

- 登录/注册
- 官网监控命令栏
- 产品库
- 情报提取
- 采集范围
- 通知日志
- 右侧日历和官网筛选

当前 UI 的主要问题：

- 首屏偏表单和说明文案，运行健康、失败风险、待处理事项不够突出。
- 产品库以卡片为主，不适合大量产品和变化事件。
- 扫描作业、通知、审计、变化事件混在通知日志里，缺少任务分组。
- 多处使用 `alert()` / `confirm()`，不适合正式上线。
- 空状态缺少诊断信息入口。
- 视觉上大圆角、玻璃拟态和卡片阴影偏原型感，不够像可长期使用的运营控制台。

## Confirmed Visual Direction

用户已选择 A 方向：macOS 控制台感，适合正式上线主平台。

设计落地判断：

- 主平台采用 macOS 风格：轻量侧栏、白灰背景、圆角克制、表格优先、状态清晰。
- 不采用 Apple Vision 全局毛玻璃作为主视觉，避免信息密度下降。
- 不采用 Apple Store 大留白作为主工作台，但登录页、空状态和引导态可以借鉴其简洁留白。
- 高级感来自精密布局、清晰排版、状态语义和顺滑反馈，而不是装饰性渐变。

## Scope

### In Scope

1. 视觉系统重构
   - 使用 `DESIGN.md` 中的新色彩、字体、间距、圆角、阴影和状态规范。
   - 减少大面积 glass effect。
   - 改成高密度控制台风格。

2. 信息架构重组
   - 左侧导航保留，但改成更紧凑的控制台导航。
   - 顶部改为 command bar + health strip。
   - 主工作区改为 table-first。
   - 右侧 rail 聚焦运行健康、失败源、待处理和当前筛选对象。

3. 产品库体验
   - 默认表格模式。
   - 保留卡片模式作为次级视图。
   - 增加筛选栏：状态、站点、置信度、时间、搜索。
   - 行内显示价格、库存、置信度、发现类型、处理状态。

4. 日志体验
   - 拆成四个子 tab：扫描作业、变化事件、通知投递、操作审计。
   - 每个 tab 使用独立列表/表格结构。

5. 反馈系统
   - 添加 toast。
   - 添加 modal。
   - 替换新增/保存/失败场景的 `alert()`。
   - 替换删除场景的 `confirm()`。

6. 空状态和 loading
   - 添加 skeleton rows。
   - 空状态显示下一步动作。
   - 产品为空时展示最近扫描摘要和采集范围状态。

7. 响应式
   - 重点验证 1440 desktop、1366 desktop、820 tablet、390 mobile。

### Out of Scope

- 不实现 scheduler worker。
- 不实现 cookie-only auth。
- 不新增数据库表。
- 不新增后端 API。
- 不改抓取策略、代理池、节点管理。
- 不引入 React/Vue 或新构建系统。

## Target Screen Architecture

### Shell

- Left rail: 232-248px.
- Main workspace: remaining width.
- Top command bar: search, URL add form trigger, refresh.
- Health strip: 4-6 compact metrics.
- Primary content: table/list surface.
- Ops rail: source health, pending actions, calendar or current site summary.

### Navigation

Navigation labels:

- 监控概览
- 产品库
- 变化事件
- 采集源
- 通知中心
- 作业日志

For first implementation, these can map to existing views without backend changes:

- `products`: 产品库
- `extraction`: 情报提取 / 字段质量
- `sources`: 采集源
- `logs`: 通知中心, internally tabbed

### Product Library

Default table columns:

- 产品
- 官网/来源
- 价格
- 库存
- 发现类型
- 置信度
- 处理状态
- 发现时间
- 操作

Row behavior:

- Click row opens detail drawer.
- Primary link opens source/product URL.
- Status buttons remain available but compact.

### Logs View

Sub tabs:

- 扫描作业: `scan_jobs`
- 变化事件: `change_events`
- 通知投递: `notification_outbox`
- 操作审计: `audit_logs`

Each tab has:

- Count badge.
- Empty state.
- Retry/action controls where applicable.

## Component Requirements

### Toast

`showToast({ type, title, message })`

Types:

- `success`
- `error`
- `warning`
- `info`

Behavior:

- Render in top-right container.
- Success/info auto dismiss after 3 seconds.
- Error/warning auto dismiss after 6 seconds.
- Close button available.

### Confirm Modal

`confirmAction({ title, message, confirmText, danger }) -> Promise<boolean>`

Behavior:

- Used for delete site/source.
- Escape closes.
- Cancel closes.
- Danger button uses error style.

### Skeleton

Used during `loadAll()`:

- Product table: 8 rows.
- Ops rail: 3 compact cards.
- Existing app can start with skeleton only when `state.user` is known and data load is pending.

## Accessibility

- Side nav current item uses `aria-current="page"`.
- Feature tabs/log tabs use `role="tablist"` and `aria-selected`.
- Icon-only controls need `aria-label`.
- Toasts use `role="status"` for success/info and `role="alert"` for error.
- Modal uses `role="dialog"` and `aria-modal="true"`.
- Touch targets >= 44px on mobile.

## Implementation Constraints

- Keep vanilla JS.
- Do not add package dependencies.
- Prefer editing `static/index.html`, `static/styles.css`, `static/app.js`.
- Reuse existing API endpoints.
- Keep all existing workflows functional.
- No hardcoded secret or environment data in frontend.
- Preserve CSV export.

## Validation

Commands:

```powershell
.\.venv\Scripts\python.exe -m app.api_smoke
.\.venv\Scripts\python.exe test_static_advanced_toggle.py
.\.venv\Scripts\python.exe test_static_monitor_settings_ui.py
.\.venv\Scripts\python.exe test_static_advanced_toggle.py
```

Browser checks:

- Open `http://127.0.0.1:8000`.
- Register/login.
- Confirm dashboard loads.
- Confirm product view empty state is useful.
- Confirm sources view still supports add/edit/scan/toggle/delete.
- Confirm logs sub tabs render without JS errors.
- Confirm toast replaces alert on add site, export failure, save success/failure.
- Confirm confirm modal replaces delete `confirm()`.

## Acceptance Criteria

- First screen looks like an operations console, not a marketing/landing page.
- Products default to table mode on desktop.
- Logs are grouped into clear sub tabs.
- Empty state tells the user what happened and what to do next.
- No `alert()` or `confirm()` remains for normal UI flows.
- Existing API smoke tests pass.
- Static UI tests pass or are updated to match the new markup.
