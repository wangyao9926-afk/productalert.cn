import { useEffect, useMemo, useState } from "react";
import {
  ArrowDown,
  Boxes,
  Clock3,
  ExternalLink,
  Eye,
  PackageCheck,
  RefreshCw,
  Search,
  Tag,
  TrendingUp,
} from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { loadOverview, type OverviewData } from "../../api/overview";
import type { ChangeEvent, Product } from "../../types/api";

function money(product: Product) {
  const value = product.price_amount ?? product.price;
  if (value === null || value === undefined || value === "") return "待采集";
  return `${product.currency || "CNY"} ${value}`;
}

function availabilityText(value?: string | null) {
  if (!value) return "未知库存";
  if (["in_stock", "available", "有货"].includes(value)) return "有货";
  if (["out_of_stock", "sold_out", "售罄"].includes(value)) return "售罄";
  return value;
}

function relativeTime(value?: string | null) {
  if (!value) return "刚刚";
  const minutes = Math.max(1, Math.round((Date.now() - new Date(value).getTime()) / 60000));
  if (minutes < 60) return `${minutes} 分钟前`;
  if (minutes < 1440) return `${Math.round(minutes / 60)} 小时前`;
  return `${Math.round(minutes / 1440)} 天前`;
}

function relatedEvents(product: Product, events: ChangeEvent[]) {
  return events.filter((event) => (
    event.product_id === product.id
    || (!!event.product_url && event.product_url === product.url)
    || (!!event.product_title && event.product_title === product.title)
  ));
}

function productType(product: Product) {
  const text = `${product.title || ""} ${product.url || ""}`.toLowerCase();
  if (/(bundle|set|kit)/.test(text)) return "套装";
  if (/(case|cover|adapter|adaptor|nozzle|hose|mats|accessory)/.test(text)) return "配件";
  if (/(clearance|sale|outlet)/.test(text)) return "清仓";
  return product.item_type === "product_detail" ? "标准商品" : "商品";
}

function siteIdFromSearch(search: string) {
  const siteId = Number(new URLSearchParams(search).get("site_id"));
  return Number.isFinite(siteId) && siteId > 0 ? siteId : null;
}

function ProductThumbnail({ product }: { product: Product }) {
  const [imageFailed, setImageFailed] = useState(false);
  const initial = (product.title || "P").trim().slice(0, 1).toUpperCase();
  return (
    <span className="product-thumb" aria-label={`${product.title || "商品"} 缩略图`}>
      {product.image_url && !imageFailed ? (
        <img src={product.image_url} alt="" onError={() => setImageFailed(true)} />
      ) : <span className="product-thumb-fallback">{initial}</span>}
    </span>
  );
}

function ProductHighlights({ product }: { product: Product }) {
  const features = product.features?.slice(0, 2).filter(Boolean) || [];
  return (
    <div className="product-highlights">
      <span className="product-type">{productType(product)}</span>
      {features.length ? features.map((feature) => <span className="product-feature" key={feature}>{feature}</span>) : (
        product.description ? <span className="product-description">{product.description.slice(0, 90)}</span> : null
      )}
    </div>
  );
}

export function ProductsPage() {
  const location = useLocation();
  const [data, setData] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [availability, setAvailability] = useState("all");
  const [selectedSiteId, setSelectedSiteId] = useState<number | null>(() => siteIdFromSearch(location.search));

  const refresh = () => {
    setLoading(true);
    loadOverview().then(setData).finally(() => setLoading(false));
  };

  useEffect(refresh, []);

  useEffect(() => setSelectedSiteId(siteIdFromSearch(location.search)), [location.search]);

  const rows = useMemo(() => {
    if (!data) return [];
    const normalizedQuery = query.trim().toLowerCase();
    return data.products
      .filter((product) => selectedSiteId === null || product.site_id === selectedSiteId)
      .map((product) => ({ product, events: relatedEvents(product, data.events) }))
      .filter(({ product }) => {
        const queryMatch = !normalizedQuery || `${product.title || ""} ${product.site_name || ""} ${product.url || ""}`.toLowerCase().includes(normalizedQuery);
        const availabilityMatch = availability === "all" || availabilityText(product.availability) === availability;
        return queryMatch && availabilityMatch;
      });
  }, [availability, data, query, selectedSiteId]);

  const changedCount = rows.filter((row) => row.events.length > 0).length;
  const inStockCount = rows.filter((row) => availabilityText(row.product.availability) === "有货").length;

  if (loading || !data) {
    return <div className="page-loading"><RefreshCw size={18} className="spin" /> 正在同步产品库...</div>;
  }

  return (
    <main className="products-page">
      <header className="page-header">
        <div>
          <div className="eyebrow">PRODUCT LIBRARY</div>
          <h1>产品库</h1>
          <p>把官网抓取结果沉淀为产品档案，集中查看缩略图、卖点、价格、库存和原站链接。</p>
          <div className={`api-status-pill ${data.live ? "success" : "warning"}`}>
            {data.live ? "真实 API" : "演示数据"} · {data.message}
          </div>
        </div>
        <div className="page-actions">
          <button className="icon-button" type="button" onClick={refresh} aria-label="刷新产品库"><RefreshCw size={17} /></button>
          <Link className="primary-button" to="/monitors/new"><Boxes size={17} /> 新建监控</Link>
        </div>
      </header>

      <section className="product-summary-grid" aria-label="产品库概览">
        <ProductMetric label="已验证商品" value={rows.length} detail={selectedSiteId ? "当前站点范围" : "当前筛选范围"} icon={<Boxes size={18} />} tone="blue" />
        <ProductMetric label="有货产品" value={inStockCount} detail="库存可售状态" icon={<PackageCheck size={18} />} tone="green" />
        <ProductMetric label="关联变化" value={changedCount} detail="存在变化事件的产品" icon={<TrendingUp size={18} />} tone="orange" />
        <ProductMetric label="来源站点" value={new Set(rows.map((row) => row.product.site_id)).size} detail="覆盖官网数量" icon={<Tag size={18} />} tone="purple" />
      </section>

      <section className="panel product-toolbar" aria-label="产品搜索">
        <div className="monitor-search">
          <Search size={15} aria-hidden="true" />
          <input value={query} onChange={(event) => setQuery(event.target.value)} type="search" placeholder="产品搜索：名称、站点或官网链接" aria-label="产品搜索" />
        </div>
        <select className="select-input compact-select" value={availability} onChange={(event) => setAvailability(event.target.value)} aria-label="库存筛选">
          <option value="all">全部库存</option>
          <option value="有货">有货</option>
          <option value="售罄">售罄</option>
          <option value="未知库存">未知库存</option>
        </select>
        <label className="site-filter-select">
          <span>按站点查看</span>
          <select value={selectedSiteId?.toString() || "all"} onChange={(event) => setSelectedSiteId(event.target.value === "all" ? null : Number(event.target.value))} aria-label="按站点查看">
            <option value="all">全部站点</option>
            {data.sites.map((site) => <option value={site.id} key={site.id}>{site.name || site.url}</option>)}
          </select>
        </label>
        <span className="monitor-count">{rows.length} 个商品</span>
      </section>

      <section className="panel products-table-panel">
        <div className="panel-heading">
          <div>
            <div className="panel-kicker">PRODUCTS</div>
            <h2>产品档案</h2>
          </div>
          <span className="tag">缩略图 / 卖点 / 价格 / 库存 / 原站链接</span>
        </div>
        {rows.length ? (
          <div className="products-table-wrap">
            <table className="products-table">
              <thead>
                <tr>
                  <th>产品</th>
                  <th>来源站点</th>
                  <th>价格</th>
                  <th>库存</th>
                  <th>关联变化</th>
                  <th>更新时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(({ product, events }) => (
                  <tr key={product.id}>
                    <td className="product-identity-cell">
                      <ProductThumbnail product={product} />
                      <div className="product-identity-copy">
                        <strong>{product.title || "未命名产品"}</strong>
                        <ProductHighlights product={product} />
                        <span className="table-sub">{product.url || product.display_url || "待采集官网链接"}</span>
                      </div>
                    </td>
                    <td>{product.site_name || "未知站点"}<span className="table-sub">{product.source_type || "未知来源"}</span></td>
                    <td><strong>{money(product)}</strong>{product.compare_at_price ? <span className="table-sub">原价 {product.compare_at_price}</span> : null}</td>
                    <td><span className={`stock-pill ${availabilityText(product.availability) === "有货" ? "in-stock" : ""}`}>{availabilityText(product.availability)}</span></td>
                    <td>{events.length ? <Link className="text-button" to={`/changes/${events[0].id}`}>{events.length} 条变化</Link> : <span className="muted">暂无变化</span>}</td>
                    <td><span className="time-cell"><Clock3 size={13} />{relativeTime(product.detected_at)}</span></td>
                    <td className="product-actions">
                      <Link className="icon-action" to={`/products/${product.id}`} title="查看详情" aria-label={`${product.title || "产品"} 查看详情`}><Eye size={14} /></Link>
                      <a className="icon-action" href={product.url || product.display_url || "#"} target="_blank" rel="noreferrer" title="打开官网" aria-label="打开官网"><ExternalLink size={14} /></a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <ProductsEmpty />}
      </section>
    </main>
  );
}

function ProductMetric({ label, value, detail, icon, tone }: { label: string; value: string | number; detail: string; icon: React.ReactNode; tone: string }) {
  return (
    <div className="metric-card product-summary-card">
      <div className={`metric-icon ${tone}`}>{icon}</div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}

function ProductsEmpty() {
  return (
    <div className="empty-state">
      <div className="empty-icon"><ArrowDown size={20} /></div>
      <h3>当前筛选下没有产品</h3>
      <p>可以调整产品搜索、库存筛选，或先创建官网监控来沉淀产品数据。</p>
    </div>
  );
}
