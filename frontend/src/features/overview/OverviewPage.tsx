import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { ArrowUpRight, CheckCircle2, Plus, RefreshCw, Sparkles, TriangleAlert } from "lucide-react";
import { Link } from "react-router-dom";
import { loadOverview, type OverviewData } from "../../api/overview";

const eventLabels: Record<string, string> = {
  new_product: "新品上架",
  variant_new: "新增变体",
  price_changed: "价格变化",
  availability_changed: "库存变化",
  content_changed: "信息变化",
};

const sourceLabels = {
  live: "真实 API",
  auth_required: "需要登录",
  api_unavailable: "演示数据 · API 不可用",
  api_error: "演示数据 · API 异常",
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

  if (!data || loading) return <div className="page-loading"><RefreshCw size={18} className="spin" /> 正在同步工作区数据...</div>;

  const actionableEvents = data.events.filter((event) => {
    const actionableType = ["new_product", "variant_new", "price_changed", "availability_changed"].includes(event.change_type || "");
    const resolved = ["reviewed", "read", "processed", "false_positive"].includes(event.inbox_status || event.status || "");
    return actionableType && !resolved;
  });
  const warningSites = data.sites
    .map((site) => ({ site, log: data.logs.find((item) => item.site_id === site.id) }))
    .filter(({ log }) => log?.status === "warning" || log?.status === "failed");
  const successfulScans = data.logs.filter((log) => log.status === "success").length;
  const scanSuccessRate = data.logs.length ? Math.round((successfulScans / data.logs.length) * 100) : 100;
  const dataMode = data.live ? sourceLabels.live : sourceLabels[data.reason];

  return (
    <main className="overview-page">
      <header className="page-header">
        <div>
          <div className="eyebrow">WORKSPACE / OVERVIEW</div>
          <h1>今天，先看要处理的事。</h1>
          <p>总览只帮助你确定下一步；看变化去收件箱，管理采集去监控中心，查完整商品去产品库。</p>
          <span className={`overview-data-mode ${data.live ? "success" : "warning"}`} title={data.message}>{dataMode}</span>
        </div>
        <div className="page-actions">
          <button className="icon-button" type="button" onClick={refresh} aria-label="刷新总览"><RefreshCw size={17} /></button>
          <Link className="primary-button" to="/monitors/new"><Plus size={17} /> 新建监控</Link>
        </div>
      </header>

      <section className="metric-grid" aria-label="今日优先级概览">
        <MetricCard label="待处理情报" value={actionableEvents.length} detail="新品、价格或库存变化" icon={<Sparkles size={19} />} tone="purple" />
        <MetricCard label="采集异常" value={warningSites.length} detail="需要在监控中心处理" icon={<TriangleAlert size={19} />} tone="orange" />
        <MetricCard label="今日新品" value={data.events.filter((event) => event.change_type === "new_product").length} detail="过去 24 小时" icon={<ArrowUpRight size={19} />} tone="green" />
        <MetricCard label="扫描成功率" value={`${scanSuccessRate}%`} detail="最近扫描表现" icon={<CheckCircle2 size={19} />} tone="blue" />
      </section>

      <div className="overview-grid">
        <section className="panel intelligence-panel">
          <div className="panel-heading">
            <div><div className="panel-kicker">TODAY ACTIONS</div><h2>优先处理</h2></div>
            <Link to="/inbox">查看情报收件箱 <ArrowUpRight size={15} /></Link>
          </div>
          <div className="event-list">
            {actionableEvents.length ? actionableEvents.slice(0, 5).map((event) => (
              <div className="event-row" key={event.id}>
                <div className={`event-icon ${event.change_type || "content_changed"}`}><Sparkles size={16} /></div>
                <div className="event-copy">
                  <div className="event-title">{event.product_title || "未命名产品"}<span className="event-type">{eventLabels[event.change_type || ""] || "信息变化"}</span></div>
                  <p>{event.summary || "检测到需要确认的变化"}</p>
                  <div className="event-meta">{event.site_name} · {relativeTime(event.created_at)}</div>
                </div>
                <Link className="text-button" to={`/changes/${event.id}`}>查看</Link>
              </div>
            )) : <OverviewEmpty icon={<CheckCircle2 size={20} />} title="暂无需要处理的情报" description="新品、价格和库存变化会在这里出现。" />}
          </div>
        </section>

        <section className="panel health-panel">
          <div className="panel-heading">
            <div><div className="panel-kicker">MONITOR HEALTH</div><h2>需要处理的站点</h2></div>
            <Link to="/monitors">打开监控中心 <ArrowUpRight size={15} /></Link>
          </div>
          <div className="health-list">
            {warningSites.length ? warningSites.slice(0, 5).map(({ site, log }) => (
              <div className="site-health" key={site.id}>
                <div className="site-avatar">{site.name.slice(0, 1)}</div>
                <div className="site-info"><strong>{site.name}</strong><span>{log?.error_message || "最近一次采集需要检查"}</span></div>
                <div className="site-status"><span className="status-dot warning" />需关注<small>{relativeTime(log?.started_at)}</small></div>
              </div>
            )) : <OverviewEmpty icon={<CheckCircle2 size={20} />} title="所有站点运行正常" description="采集失败、限流或解析异常会在这里优先提示。" />}
          </div>
        </section>
      </div>
    </main>
  );
}

function MetricCard({ label, value, detail, icon, tone }: { label: string; value: string | number; detail: string; icon: ReactNode; tone: string }) {
  return <div className="metric-card"><div className={`metric-icon ${tone}`}>{icon}</div><div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div></div>;
}

function OverviewEmpty({ icon, title, description }: { icon: ReactNode; title: string; description: string }) {
  return <div className="overview-empty"><div className="empty-icon">{icon}</div><div><strong>{title}</strong><p>{description}</p></div></div>;
}
