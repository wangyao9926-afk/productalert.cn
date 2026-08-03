import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  Boxes,
  Clock3,
  ExternalLink,
  FileText,
  Link2,
  PackageCheck,
  RefreshCw,
  ShieldAlert,
  Tag,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { loadProductDetailContext, type ProductDetailContext } from "../../api/products";
import type { ChangeEvent, Product } from "../../types/api";

function money(product?: Product | null) {
  if (!product) return "待采集";
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

function variantPrice(value?: number | null, fallback?: string | null, currency?: string | null) {
  if (value !== null && value !== undefined) return `${currency || "CNY"} ${value}`;
  return fallback || "待采集";
}

function relativeTime(value?: string | null) {
  if (!value) return "刚刚";
  const minutes = Math.max(1, Math.round((Date.now() - new Date(value).getTime()) / 60000));
  if (minutes < 60) return `${minutes} 分钟前`;
  if (minutes < 1440) return `${Math.round(minutes / 60)} 小时前`;
  return `${Math.round(minutes / 1440)} 天前`;
}

function eventLabel(event: ChangeEvent) {
  if (event.change_type === "new_product" || event.change_type === "product_new") return "新品上新";
  if (event.change_type === "variant_new") return "新增变体";
  if (event.change_type === "price_changed" || event.change_type === "price_change") return "价格变化";
  if (event.change_type === "availability_changed" || event.change_type === "availability_change") return "库存变化";
  return "信息变化";
}

export function ProductDetailPage() {
  const { id } = useParams();
  const [data, setData] = useState<ProductDetailContext | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = () => {
    setLoading(true);
    loadProductDetailContext(id || "").then(setData).finally(() => setLoading(false));
  };

  useEffect(refresh, [id]);

  const product = data?.product;
  const site = useMemo(() => data?.sites.find((item) => item.id === product?.site_id), [data?.sites, product?.site_id]);

  if (loading || !data) {
    return <div className="page-loading"><RefreshCw size={18} className="spin" /> 正在加载产品详情...</div>;
  }

  if (!product) {
    return (
      <main className="product-detail-page">
        <section className="page-state panel">
          <span className="eyebrow">PRODUCT NOT FOUND</span>
          <h1>产品详情</h1>
          <p>没有找到该产品记录。可能产品属于演示数据之外，或当前账号没有访问权限。</p>
          <Link className="primary-button" to="/products"><ArrowLeft size={16} /> 返回产品库</Link>
        </section>
      </main>
    );
  }

  return (
    <main className="product-detail-page">
      <header className="page-header">
        <div>
          <Link className="back-link" to="/products"><ArrowLeft size={15} /> 返回产品库</Link>
          <div className="eyebrow">PRODUCT DETAIL</div>
          <h1>产品详情</h1>
          <p>{product.title || "未命名产品"} · {product.site_name || site?.name || "未知站点"}</p>
          <div className={`api-status-pill ${data.live ? "success" : "warning"}`}>
            {data.live ? "真实 API" : "演示数据"} · {data.message}
          </div>
        </div>
        <div className="page-actions">
          <button className="icon-button" type="button" onClick={refresh} aria-label="刷新产品详情"><RefreshCw size={17} /></button>
          <a className="primary-button" href={product.url || product.display_url || "#"} target="_blank" rel="noreferrer"><ExternalLink size={17} /> 打开官网</a>
        </div>
      </header>

      <section className="detail-summary-grid" aria-label="价格与库存">
        <ProductMetric label="当前价格" value={money(product)} detail={product.compare_at_price ? `原价 ${product.compare_at_price}` : "价格与库存"} icon={<Tag size={18} />} tone="blue" />
        <ProductMetric label="库存状态" value={availabilityText(product.availability)} detail="来自最近一次抓取" icon={<PackageCheck size={18} />} tone="green" />
        <ProductMetric label="关联变化事件" value={data.events.length} detail="新品、价格、库存、信息变化" icon={<FileText size={18} />} tone="orange" />
        <ProductMetric label="来源站点" value={product.site_name || site?.name || "未知站点"} detail={product.source_type || "未知来源"} icon={<Boxes size={18} />} tone="purple" />
      </section>

      <div className="product-detail-grid">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <div className="panel-kicker">PROFILE</div>
              <h2>产品档案</h2>
            </div>
            <span className="tag">价格与库存</span>
          </div>
          <dl className="metadata-list">
            <div><dt>产品名称</dt><dd>{product.title || "未命名产品"}</dd></div>
            <div><dt>官网链接</dt><dd><a href={product.url || product.display_url || "#"} target="_blank" rel="noreferrer"><Link2 size={13} /> {product.url || product.display_url || "待采集"}</a></dd></div>
            <div><dt>价格</dt><dd>{money(product)}</dd></div>
            <div><dt>库存</dt><dd>{availabilityText(product.availability)}</dd></div>
            <div><dt>SKU / 变体</dt><dd>{product.variant_count ?? "待采集"}</dd></div>
            <div><dt>发现时间</dt><dd>{relativeTime(product.detected_at)}</dd></div>
          </dl>
        </section>

        <section className="panel">
          <div className="panel-heading">
            <div>
              <div className="panel-kicker">QUALITY</div>
              <h2>数据质量</h2>
            </div>
          </div>
          <div className="quality-stack">
            <QualityItem label="价格字段" ready={money(product) !== "待采集"} />
            <QualityItem label="库存字段" ready={availabilityText(product.availability) !== "未知库存"} />
            <QualityItem label="官网链接" ready={!!(product.url || product.display_url)} />
            <QualityItem label="关联变化" ready={data.events.length > 0} />
          </div>
        </section>
      </div>

      <section className="panel related-events-panel">
        <div className="panel-heading">
          <div>
            <div className="panel-kicker">VERIFIED IDENTITY</div>
            <h2>同款匹配</h2>
          </div>
          <span className="monitor-count">{data.matches.length} 组</span>
        </div>
        {data.matches.length ? data.matches.map((group) => (
          <div className="match-group" key={group.id}>
            <p className="table-sub">精确 {group.identifier_type.toUpperCase()}：{group.identifier_value}</p>
            <div className="table-wrap">
              <table>
                <thead><tr><th>站点</th><th>商品</th><th>价格</th><th>库存</th></tr></thead>
                <tbody>{group.products.map((match) => (
                  <tr key={match.id}>
                    <td>{match.site_name || "未知站点"}</td>
                    <td><a href={match.url || "#"} target="_blank" rel="noreferrer">{match.title || `#${match.id}`}</a></td>
                    <td>{variantPrice(match.price_amount, match.price, match.currency)}</td>
                    <td><span className="tag">{availabilityText(match.availability)}</span></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </div>
        )) : (
          <div className="empty-state compact"><div className="empty-icon"><Boxes size={18} /></div><p>暂未发现拥有完全相同 GTIN 或 SKU 的跨站商品。</p></div>
        )}
      </section>

      <section className="panel related-events-panel">
        <div className="panel-heading">
          <div>
            <div className="panel-kicker">VARIANTS</div>
            <h2>颜色 / 尺码变体</h2>
          </div>
          <span className="monitor-count">{data.variants.length} 条</span>
        </div>
        {data.variants.length ? (
          <div className="table-wrap">
            <table>
              <thead><tr><th>变体</th><th>SKU</th><th>选项</th><th>价格</th><th>库存</th></tr></thead>
              <tbody>{data.variants.map((variant) => (
                <tr key={variant.id}>
                  <td><strong>{variant.title || variant.external_id}</strong><span className="table-sub">#{variant.external_id}</span></td>
                  <td>{variant.sku || "未采集"}</td>
                  <td>{variant.option_values || "未采集"}</td>
                  <td>{variantPrice(variant.price_amount, variant.price, product.currency)}<span className="table-sub">{variant.compare_at_price ? `划线价 ${variant.compare_at_price}` : ""}</span></td>
                  <td><span className="tag">{variant.is_active ? availabilityText(variant.availability) : "已下架"}</span></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state compact"><div className="empty-icon"><Boxes size={18} /></div><p>该商品暂无可识别的变体数据</p></div>
        )}
      </section>

      <section className="panel related-events-panel">
        <div className="panel-heading">
          <div>
            <div className="panel-kicker">CHANGE EVENTS</div>
            <h2>关联变化事件</h2>
          </div>
          <span className="monitor-count">{data.events.length} 条</span>
        </div>
        {data.events.length ? (
          <div className="event-list compact">
            {data.events.map((event) => (
              <article className="event-row" key={event.id}>
                <div className="event-icon"><FileText size={15} /></div>
                <div className="event-copy">
                  <div className="event-title">{event.summary || "检测到产品变化"} <span className="event-type">{eventLabel(event)}</span></div>
                  <p>{event.site_name || product.site_name || "未知站点"} · {relativeTime(event.created_at)}</p>
                </div>
                <Link className="text-button" to={`/changes/${event.id}`}>查看变化详情</Link>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <div className="empty-icon"><ShieldAlert size={20} /></div>
            <h3>暂无关联变化事件</h3>
            <p>后续价格、库存、信息变化会沉淀在这里，便于运营复盘。</p>
          </div>
        )}
      </section>
    </main>
  );
}

function ProductMetric({ label, value, detail, icon, tone }: { label: string; value: string | number; detail: string; icon: React.ReactNode; tone: string }) {
  return (
    <div className="metric-card detail-metric-card">
      <div className={`metric-icon ${tone}`}>{icon}</div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}

function QualityItem({ label, ready }: { label: string; ready: boolean }) {
  return (
    <div className={`quality-item ${ready ? "ready" : ""}`}>
      <span>{ready ? "已采集" : "待完善"}</span>
      <strong>{label}</strong>
    </div>
  );
}
