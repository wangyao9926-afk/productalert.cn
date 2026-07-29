# 官网新品情报监控系统产品蓝图

## 1. 产品一句话

面向品牌、选品、运营和竞品研究人员的官网新品情报监控系统，帮助用户持续发现品牌官网新品发布，提取完整新品信息，分析功能卖点，并把情报沉淀到可检索、可通知、可复盘的工作台。

## 2. 目标用户

### 品牌人员

关注自家和竞品官网的新品节奏、产品表达、定价、卖点和活动信息。

### 选品人员

关注目标品牌是否发布新品、产品是否符合选品方向、是否值得进入后续跟进。

### 运营人员

关注新品发布时间、促销节点、页面文案、素材图片和传播角度。

### 竞品研究人员

关注竞品产品线变化、功能升级、价格策略、市场定位和页面叙事变化。

## 3. 产品边界

### 我们要做

- 监控公开官网、产品页、新闻页、发布页、sitemap、RSS 和用户指定页面。
- 发现疑似新品和重要页面变化。
- 提取产品信息、功能卖点、规格参数、价格、图片和发布时间。
- 用 AI 做分类、摘要、卖点提炼和置信度判断。
- 提供通知、工作台、状态管理、搜索筛选和导出。

### 我们暂时不做

- 绕过登录、验证码、付费墙、访问控制或反爬限制。
- 采集非公开数据、个人数据或敏感数据。
- 代替人工做最终商业判断。
- 直接复制第三方工具的完整交互和商业实现。

## 4. 四大模块

### 4.1 新品监控模块

目标：回答“这个品牌有没有发新品？”

核心能力：

- 品牌档案：品牌名、官网、地区、品类、备注、重要程度。
- 监控源：官网首页、sitemap、RSS、产品集合页、新闻页、用户指定 URL。
- 发现策略：自动发现产品链接、手动配置列表页、关键词识别、排除词过滤。
- 首次基线：第一次扫描只建立已知页面库，不默认通知。
- 新品判定：新增 URL、新增 sitemap 条目、新增列表项、发布时间较新、页面包含新品语义。
- 误报控制：低置信度进入待复核，不直接推送强提醒。

关键状态：

- 未扫描
- 建立基线中
- 监控中
- 发现疑似新品
- 已确认新品
- 已忽略
- 检查失败

### 4.2 页面变化监控模块

目标：回答“页面哪里变了，变了什么？”

核心能力：

- 整页监控：页面 HTML、正文文本、关键 meta 信息。
- 区域监控：CSS selector、XPath 或用户可视化选择的区域。
- 元素监控：价格、库存、按钮、标题、发布时间等字段。
- 视觉监控：定时截图、像素差异、变化区域标注。
- 快照保存：保存变化前后的 HTML、文本、截图和字段值。
- 变化摘要：展示新增、删除、修改的文本片段。

适用场景：

- 价格变动
- 库存状态变化
- 活动页面更新
- 新增版块
- 产品详情页文案更新
- 官网首页大促或新品入口变化

### 4.3 AI 新品情报分析模块

目标：回答“这个新品是什么，为什么重要？”

核心能力：

- 页面分类：新品、产品详情、新闻稿、促销、补货、普通更新、无关页面。
- 信息抽取：产品名、品牌、品类、价格、规格、图片、发布时间、购买入口。
- 卖点提炼：功能卖点、成分/参数、适用人群、场景、差异化表达。
- 情报摘要：一句话简报、3-5 个核心卖点、运营关注点、竞品观察。
- 置信度：对新品判断和字段抽取分别打分。
- 人工复核：低置信度或高价值品牌进入待确认队列。

输出结构建议：

```json
{
  "type": "new_product",
  "confidence": 0.86,
  "brand": "Example Brand",
  "product_name": "Example Product",
  "category": "Skin Care",
  "launch_date": "2026-07-01",
  "price": "¥299",
  "summary": "品牌发布了一款主打修护和敏感肌场景的新精华。",
  "features": ["主打屏障修护", "适合敏感肌", "新增复配成分"],
  "target_audience": ["敏感肌用户", "修护需求用户"],
  "source_url": "https://example.com/product/example"
}
```

### 4.4 通知与工作台模块

目标：回答“谁需要知道，后续怎么处理？”

核心能力：

- 通知渠道：企业微信、飞书、钉钉、邮件、Telegram、Webhook。
- 通知规则：按品牌、品类、关键词、重要程度、置信度、价格变化路由。
- 工作台收件箱：未读、已读、重要、待复核、待跟进、已归档。
- 新品时间线：按品牌和时间展示新品发布节奏。
- 竞品库：按品牌沉淀历史新品和变化记录。
- 搜索筛选：品牌、品类、关键词、时间、状态、置信度。
- 导出：Excel、CSV、Markdown 简报。

## 5. 数据模型草案

### Brand

- id
- name
- website_url
- region
- category
- priority
- notes
- created_at
- updated_at

### MonitorSource

- id
- brand_id
- type: homepage | sitemap | rss | listing_page | detail_page | visual_area
- url
- selector
- include_keywords
- exclude_keywords
- scan_interval_minutes
- enabled
- baseline_completed_at

### Snapshot

- id
- source_id
- url
- fetched_at
- http_status
- content_hash
- text_hash
- screenshot_path
- html_path
- extracted_text

### ChangeEvent

- id
- source_id
- snapshot_before_id
- snapshot_after_id
- change_type: new_url | text_change | visual_change | field_change
- severity
- summary
- diff_json
- created_at

### IntelligenceItem

- id
- brand_id
- source_event_id
- type: new_product | product_update | promo | restock | irrelevant
- confidence
- title
- product_name
- price
- image_url
- source_url
- summary
- features_json
- extracted_fields_json
- review_status
- created_at

### NotificationRule

- id
- name
- channel
- target_url
- brand_filter
- keyword_filter
- min_confidence
- min_severity
- enabled

## 6. 安全和可靠性原则

- 只监控公开网页，不绕过登录、验证码、付费墙或访问控制。
- 尊重站点访问压力，默认低频检查，支持单站点限速和失败退避。
- 保存抓取日志、HTTP 状态和错误原因，便于排查。
- Webhook、API Key 等敏感配置后续放入 `.env` 或加密存储，不写入前端。
- AI 输出必须保留来源链接和原文证据，避免无法追溯。
- 高风险自动判断必须给出置信度，低置信度进入人工复核。
- 通知去重，避免同一新品重复轰炸。
- 数据库需要迁移机制，避免后续功能升级破坏历史数据。

## 7. 分阶段路线图

### Phase 1: 严谨监控基础

- 品牌档案
- 监控源管理
- 首次扫描建基线
- 新增 URL 检测
- 手动指定新品页
- 扫描日志和失败原因

当前实现状态：品牌档案、多个监控源、首次基线、新增 URL 检测、手动指定页面和扫描日志已经进入本地原型。后续需要继续补监控源编辑、规则测试、扫描限速和更完整的失败重试。

### Phase 2: 变化监控和快照

- HTML/text 快照
- 字段变化记录
- 文本 diff
- CSS selector 监控
- 页面截图和视觉变化基础能力

当前实现状态：CSS selector 手动输入、文本快照、文本变化事件、diff 高亮和收件箱状态已经进入本地原型。后续需要补字段级变化、截图快照、视觉差异和可视化点选区域。

### Phase 3: AI 情报分析

- 页面分类
- 新品字段结构化抽取
- 卖点和摘要生成
- 置信度
- 人工复核流

### Phase 4: 通知和工作台

- 通知规则
- 多渠道通知
- 状态流转
- 搜索筛选
- 导出
- 品牌新品时间线

### Phase 5: 体验和规模化

- 可视化选择监控区域
- 队列化扫描
- 多用户和权限
- 团队协作
- UI 视觉升级
- 部署和备份方案

## 8. 当前优先级

下一步先做 Phase 1，不急着美化 UI：

1. 把“站点”升级为“品牌档案”。
2. 增加“监控源”概念，不再只有一个官网 URL。
3. 增加首次扫描建基线，不把历史页面当新品。
4. 增加扫描日志，用户能知道为什么成功或失败。
5. 增加手动配置新品列表页和关键词规则。
