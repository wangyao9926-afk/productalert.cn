import { ExternalLink, RefreshCw, ShieldCheck, TableProperties } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { loadPriceMatrix, type ProductMatchGroup } from "../../api/products";

function priceLabel(item: ProductMatchGroup["products"][number]) {
  const value = item.price_amount ?? item.price;
  return value === null || value === undefined || value === "" ? "待采集" : `${item.currency || "—"} ${value}`;
}

function availabilityLabel(value?: string | null) {
  if (value === "in_stock" || value === "available") return "有货";
  if (value === "out_of_stock" || value === "sold_out") return "售罄";
  return value || "未知";
}

export function PriceMatrixPage() {
  const [groups, setGroups] = useState<ProductMatchGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = () => {
    setLoading(true);
    setError("");
    loadPriceMatrix().then(setGroups).catch(() => setError("无法加载价格矩阵，请确认已登录且 API 服务正常。"))
      .finally(() => setLoading(false));
  };

  useEffect(refresh, []);

  const products = useMemo(() => groups.flatMap((group) => group.products), [groups]);
  const siteCount = useMemo(() => new Set(products.map((product) => product.site_id)).size, [products]);

  if (loading) return <div className="page-loading"><RefreshCw size={18} className="spin" /> 正在加载价格矩阵…</div>;

  return (
    <main className="price-matrix-page">
      <header className="page-header">
        <div>
          <div className="eyebrow">VERIFIED COMPETITOR INTELLIGENCE</div>
          <h1>竞品价格矩阵</h1>
          <p>只展示通过精确 GTIN 或 SKU 验证的跨站同款；价格按采集币种原样呈现，不进行汇率换算。</p>
        </div>
        <div className="page-actions">
          <button className="icon-button" type="button" onClick={refresh} aria-label="刷新价格矩阵"><RefreshCw size={17} /></button>
          <Link className="primary-button" to="/products"><TableProperties size={17} /> 查看产品库</Link>
        </div>
      </header>

      <section className="price-matrix-summary" aria-label="价格矩阵概览">
        <Metric label="已验证同款组" value={groups.length} detail="精确 GTIN / SKU" />
        <Metric label="覆盖商品" value={products.length} detail="参与跨站比价的商品" />
        <Metric label="覆盖站点" value={siteCount} detail="当前可比较的数据来源" />
      </section>

      <section className="panel price-matrix-panel">
        <div className="panel-heading">
          <div><div className="panel-kicker">PRICE MATRIX</div><h2>已验证跨站报价</h2></div>
          <span className="tag"><ShieldCheck size={13} /> 仅精确身份匹配</span>
        </div>
        {error ? <div className="empty-state"><p>{error}</p></div> : groups.length ? groups.map((group) => (
          <div className="matrix-group" key={group.id}>
            <div className="matrix-group-title">
              <strong>{group.identifier_type.toUpperCase()}：{group.identifier_value}</strong>
              <span>{group.products.length} 个站点商品</span>
            </div>
            <div className="table-wrap">
              <table className="price-matrix-table">
                <thead><tr><th>站点</th><th>商品</th><th>价格</th><th>库存</th><th>产品档案</th></tr></thead>
                <tbody>{group.products.map((product) => (
                  <tr key={product.id}>
                    <td><strong>{product.site_name || "未知站点"}</strong></td>
                    <td><a href={product.url || "#"} target="_blank" rel="noreferrer">{product.title || `#${product.id}`} <ExternalLink size={12} /></a></td>
                    <td><strong>{priceLabel(product)}</strong></td>
                    <td><span className="stock-pill">{availabilityLabel(product.availability)}</span></td>
                    <td><Link className="text-button" to={`/products/${product.id}`}>查看证据</Link></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </div>
        )) : <div className="empty-state"><div className="empty-icon"><ShieldCheck size={20} /></div><h3>尚无可比价的验证同款</h3><p>当两个或更多站点出现完全相同的 GTIN 或 SKU 后，它们会自动进入此矩阵。</p></div>}
      </section>
    </main>
  );
}

function Metric({ label, value, detail }: { label: string; value: number; detail: string }) {
  return <div className="metric-card price-matrix-metric"><div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div></div>;
}
