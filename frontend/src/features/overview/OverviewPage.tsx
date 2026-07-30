import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { ArrowUpRight, BellRing, CheckCircle2, Clock3, Database, ExternalLink, Plus, RefreshCw, Server, Sparkles, TriangleAlert } from "lucide-react";
import { Link } from "react-router-dom";
import { loadOverview, type OverviewData } from "../../api/overview";

const eventLabels: Record<string, string> = { new_product: "新品上架", variant_new: "新增变体", price_changed: "价格变化", availability_changed: "库存变化", content_changed: "信息变化" };
const sourceLabels = {
  live: "真实 API",
  auth_required: "需要登录",
  api_unavailable: "API 不可用",
  api_error: "API 异常",
} as const;

function relativeTime(value?: string | null) {
  if (!value) return "刚刚";
  const minutes = Math.max(1, Math.round((Date.now() - new Date(value).getTime()) / 60000));
  return minutes < 60 ? `${minutes} 分钟前` : `${Math.round(minutes / 60)} 小时前`;
}

export function OverviewPage() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const refresh = () => { setLoading(true); loadOverview().then(setData).finally(() => setLoading(false)); };
  useEffect(refresh, []);
  if (!data || loading) return <div className="page-loading"><RefreshCw size={18} className="spin" /> 正在同步工作区数据…</div>;
  const unread = data.events.filter((event) => event.status !== "reviewed").length;
  const healthy = data.logs.filter((log) => log.status === "success").length;
  return <main className="overview-page">
    <header className="page-header">
      <div><div className="eyebrow">WORKSPACE / OVERVIEW</div><h1>今天，先看变化。</h1><p>把新品、价格和站点健康集中到一个可执行的工作台。</p></div>
      <div className="page-actions"><button className="icon-button" onClick={refresh} aria-label="刷新"><RefreshCw size={17} /></button><Link className="primary-button" to="/monitors/new"><Plus size={17} /> 新建监控</Link></div>
    </header>
    <section className="health-strip" aria-label="系统状态">
      <div className="health-primary"><span className={`status-dot ${data.live ? "success" : "warning"}`} /> {data.live ? "监控系统正常" : "演示数据"} <span className="muted">· {sourceLabels[data.reason]}</span></div>
      <div className="health-item data-source-message"><RefreshCw size={15} /> 数据来源<strong>{data.message}</strong></div>
      <div className="health-item"><Database size={15} /> {data.health.database_backend || "database"}<strong>在线</strong></div>
      <div className="health-item"><Server size={15} /> {data.health.queue_backend || "queue"}<strong>{data.health.background_workers_enabled ? "运行中" : "待启动"}</strong></div>
      <div className="health-item"><BellRing size={15} /> 通知通道<strong>{data.health.notification_worker_enabled ? "正常" : "待配置"}</strong></div>
    </section>
    <section className="metric-grid">
      <MetricCard label="监控站点" value={data.sites.length} detail="活跃站点" icon={<GlobeIcon />} tone="blue" />
      <MetricCard label="待处理情报" value={unread} detail="需要人工确认" icon={<Sparkles size={19} />} tone="purple" />
      <MetricCard label="今日新品" value={data.events.filter((e) => e.change_type === "new_product").length} detail="过去 24 小时" icon={<ArrowUpRight size={19} />} tone="green" />
      <MetricCard label="扫描成功率" value={`${data.logs.length ? Math.round((healthy / data.logs.length) * 100) : 100}%`} detail="最近 100 次扫描" icon={<CheckCircle2 size={19} />} tone="orange" />
    </section>
    <div className="overview-grid">
      <section className="panel intelligence-panel"><div className="panel-heading"><div><div className="panel-kicker">INTELLIGENCE INBOX</div><h2>待处理情报</h2></div><Link to="/inbox">查看全部 <ArrowUpRight size={15} /></Link></div><div className="event-list">{data.events.slice(0, 5).map((event) => <div className="event-row" key={event.id}><div className={`event-icon ${event.change_type || "content_changed"}`}><Sparkles size={16} /></div><div className="event-copy"><div className="event-title">{event.product_title || "未命名产品"}<span className="event-type">{eventLabels[event.change_type || ""] || "信息变化"}</span></div><p>{event.summary || "检测到页面变化"}</p><div className="event-meta">{event.site_name} · {relativeTime(event.created_at)}</div></div><button className="text-button">审阅</button></div>)}</div></section>
      <section className="panel health-panel"><div className="panel-heading"><div><div className="panel-kicker">MONITOR HEALTH</div><h2>站点健康</h2></div><Link to="/monitors">管理 <ArrowUpRight size={15} /></Link></div><div className="health-list">{data.sites.map((site) => { const log = data.logs.find((item) => item.site_id === site.id); return <div className="site-health" key={site.id}><div className="site-avatar">{site.name.slice(0, 1)}</div><div className="site-info"><strong>{site.name}</strong><span>{site.url}</span></div><div className="site-status"><span className={`status-dot ${log?.status === "warning" ? "warning" : "success"}`} />{log?.status === "warning" ? "需关注" : "正常"}<small>{log ? `${log.duration_ms || 0}ms` : "尚未扫描"}</small></div></div> })}</div></section>
    </div>
    <section className="panel changes-panel"><div className="panel-heading"><div><div className="panel-kicker">RECENT CHANGES</div><h2>最近变化</h2></div><Link to="/changes">打开变化时间线 <ArrowUpRight size={15} /></Link></div><div className="table-wrap"><table><thead><tr><th>产品</th><th>变化类型</th><th>站点</th><th>检测时间</th><th /></tr></thead><tbody>{data.events.map((event) => <tr key={event.id}><td><strong>{event.product_title || "未命名产品"}</strong><span className="table-sub">{event.summary}</span></td><td><span className="tag">{eventLabels[event.change_type || ""] || "信息变化"}</span></td><td>{event.site_name || "—"}</td><td><span className="time-cell"><Clock3 size={14} />{relativeTime(event.created_at)}</span></td><td><ExternalLink size={15} className="muted" /></td></tr>)}</tbody></table></div></section>
  </main>;
}

function MetricCard({ label, value, detail, icon, tone }: { label: string; value: string | number; detail: string; icon: ReactNode; tone: string }) { return <div className="metric-card"><div className={`metric-icon ${tone}`}>{icon}</div><div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div></div>; }
function GlobeIcon() { return <span className="globe-icon">◉</span>; }
