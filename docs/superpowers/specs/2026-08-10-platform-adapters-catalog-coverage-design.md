# 平台适配器与目录覆盖设计

## 目标

让首轮基线扫描能够说明“商品是从哪里发现的、发现了多少、是否已经完整验证”，并把商品发现从仅依赖 URL 规则扩展到公开 Shopify、WooCommerce Store API 与通用 JSON-LD 目录。系统不会绕过访问控制、登录或限流。

## 当前事实与问题

现有抓取器已支持 Shopify `products.json`、Sitemap、首页链接和商品页 JSON-LD，但发现顺序未把公开平台目录作为主证据保存。`discover_candidates()` 只返回候选 URL；扫描任务无法区分候选来自 Shopify、Sitemap、集合页还是 JSON-LD。WooCommerce 的公开 Store API 也尚未接入。因此，用户看到的已入库数难以与站点公开目录数量进行核对。

## 范围

本切片只覆盖公开目录发现、发现证据和扫描质量展示：

- Shopify 公开 `products.json` 优先发现，随后才使用 Sitemap、集合页/首页链接和 JSON-LD 补充。
- WooCommerce Store API (`/wp-json/wc/store/v1/products`) 分页发现公开商品。
- 从页面 JSON-LD `ItemList` 中发现商品 URL，并保留 JSON-LD 为发现来源。
- 同一候选可同时记录多个发现来源；规范化 URL 后去重。
- 扫描结果保存并展示目录参考总数、按来源发现数、已验证数、待验证数与覆盖状态。
- HTTP 403、429、超时、格式错误和没有公开目录都必须被明确分类；429 仍沿用域名冷却与“基线不完整”逻辑。

不包含：私有 WooCommerce API、代理池、规避反爬、登录态抓取、Magento/SFCC 适配器、地区切换、价格矩阵。

## 方案选择

考虑过三种方式：

1. 只扩大 URL 正则规则：改动最小，但无法证明目录覆盖，也不能发现非 `/product/` 形式的 WooCommerce URL。
2. 为每个平台直接写入产品库：速度快，但会绕过统一的抓取证据与字段验证路径，后续变化检测不一致。
3. **推荐：统一目录发现适配器，继续使用已有商品提取与入库路径。** 平台适配器只产生带来源证据的 `ProductCandidate`，扫描器仍对每个候选执行已有的证据、字段、变体及变化处理。这样可复用现有的限流、失败分类与恢复机制。

## 架构与数据流

新增一个仅在抓取层使用的 `CatalogDiscoveryResult`：

- `candidates`：规范化、去重后的 `ProductCandidate` 列表；每个候选携带 `discovery_sources` 与可选公开 API payload。
- `reference_counts`：可公开核对的目录数。例如 Shopify 和 WooCommerce 分页完整返回后记录其商品数；Sitemap/HTML/JSON-LD 仅记录发现数，不冒充站点总数。
- `attempts`：每个适配器的状态、HTTP 结果与失败类别，供扫描质量说明使用。

`discover_catalog()` 按下列顺序运行，任一可用来源都可补充候选，而不是覆盖前一来源：

1. Shopify `products.json`，每页最多 250 项，直到短页；HTTP 404/非 JSON 代表“不适用”，429/403/网络错误写入适配器结果。
2. WooCommerce Store API，每页最多 100 项，使用响应的 `X-WP-Total`（若有）作为参考总数；只使用 API 返回的公开 permalink、名称与数据载荷。
3. 主 Sitemap 与产品子 Sitemap；产品 URL 作为候选，其他 URL 仅作辅助发现。
4. 源页及发现到的集合页；从 a 标签和 JSON-LD `ItemList` 补充候选。
5. 仅当候选过少时，复用现有浏览器渲染回退。

适配器以共享的候选合并函数去重：canonical URL 是主键；合并同 URL 的标题、payload 与 `discovery_sources`。来自平台 payload 或 JSON-LD 明确 Product 的候选，即使 URL 不符合 `/product(s)/` 规则，也视为商品候选。未知的普通链接仍须通过现有 URL 分类过滤。

扫描器调用 `discover_catalog()`，把质量结果写入现有 `scan_jobs.result.progress.quality` JSON，不新增数据库表：

- `catalog_reference_count`：只有某一公开平台分页正常结束时才有值；没有可信平台参考数则为 `null`。
- `discovery_source_counts`：如 `shopify_api`、`woocommerce_store_api`、`product_sitemap`、`html_links`、`json_ld_item_list`。
- `adapter_attempts`：每项包含 adapter、status（`available`/`not_applicable`/`limited`/`blocked`/`failed`）、HTTP 状态和简短原因。
- `coverage_state`：`verified` 仅在无待验证候选且可信平台目录参考数与发现/验证路径没有冲突时出现；其余成功但无总量证据为 `best_effort`；存在 429、403 或待重试候选为 `incomplete`；无商品且所有适配器失败为 `failed`。

既有 `baseline_state` 继续决定能否触发新品事件；`coverage_state` 只解释目录覆盖，不能放宽基线完成条件。

## API 与界面

不增加新的公开端点。既有 `GET /api/scan-jobs/{job_id}` 与 `GET /api/sites/{site_id}/baseline-summary` 在质量对象中返回上述字段。

首次扫描页新增一张“目录覆盖”信息卡：

- 有参考数时：`已验证 N / 目录参考 M`，同时显示覆盖状态。
- 无参考数时：`已验证 N，未取得公开目录总数`，不得显示百分比或“全量”。
- 显示来源 chips 与受限流/失败的适配器说明。
- `incomplete` 保留现有“继续扫描”入口；`best_effort` 说明当前是公开证据下的尽力发现，不暗示全量。

## 错误处理与合规

- 每个 HTTP 请求继续先做 URL 安全校验并遵守域名节流。
- 收到 429 时读取 `Retry-After`、记录冷却并停止该适配器的后续分页；不得切换代理或伪造身份继续请求。
- 403 标记为 `blocked`；404 和不符合预期的 JSON 标记为 `not_applicable`，不会让整个扫描直接失败。
- 适配器失败后允许其它公开来源继续发现；若提取阶段遇到 429，沿用当前候选暂停与恢复机制。

## 测试与验收

先写失败测试，再实现：

1. Shopify、WooCommerce 与 JSON-LD ItemList 的候选可以合并，且保留所有来源。
2. WooCommerce 正常分页时记录 `X-WP-Total` 为参考数；429 时记录受限流且不继续分页。
3. 具有 WooCommerce/JSON-LD 明确信号、但 URL 不含 `/product/` 的候选仍会进入商品提取。
4. 扫描任务把来源计数、适配器状态和覆盖状态返回给 API；存在待重试候选时必为 `incomplete`。
5. 前端契约测试覆盖“有目录参考数”和“无可信总量”两种文案，确保不会将已入库数称为全站总数。

验收时不对真实站点高频扫描。离线 fixture 验证适配器分页、429 和去重；本地应用手动创建一个公开站点监控，页面应能显示来源与覆盖说明。若公开站点返回 429，验收结果只能是可解释的 `incomplete`，不能宣称商品总数正确。
