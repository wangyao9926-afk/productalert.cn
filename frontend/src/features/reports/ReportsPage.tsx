import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Boxes,
  Clock3,
  Download,
  PackagePlus,
  RefreshCw,
  ShieldCheck,
  Tag,
  TrendingUp,
} from "lucide-react";
import { Link } from "react-router-dom";
import { loadChangeEvents } from "../../api/changes";
import { loadOverview, type OverviewData } from "../../api/overview";
import type { ChangeEvent, ScanLog, Site } from "../../types/api";

type TrendBucket = {
  label: string;
  newProductCount: number;
  priceChangeCount: number;
  stockChangeCount: number;
  infoChangeCount: number;
};

function dayLabel(offset: number) {
  const date = new Date();
  date.setDate(date.getDate() - offset);
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

function isSameDay(value: string | null | undefined, offset: number) {
  if (!value) return offset === 0;
  const target = new Date();
  target.setDate(target.getDate() - offset);
  const date = new Date(value);
  return date.getFullYear() === target.getFullYear()
    && date.getMonth() === target.getMonth()
    && date.getDate() === target.getDate();
}

function eventKind(event: ChangeEvent) {
  const type = event.change_type || "";
  if (type === "new_product" || type === "product_new" || type === "variant_new") return "new";
  if (type === "price_changed" || type === "price_change") return "price";
  if (type === "availability_changed" || type === "availability_change") return "stock";
  return "info";
}

function buildTrendBuckets(events: ChangeEvent[]): TrendBucket[] {
  return Array.from({ length: 7 }, (_, index) => {
    const offset = 6 - index;
    const dayEvents = events.filter((event) => isSameDay(event.created_at, offset));
    return {
      label: dayLabel(offset),
      newProductCount: dayEvents.filter((event) => eventKind(event) === "new").length,
      priceChangeCount: dayEvents.filter((event) => eventKind(event) === "price").length,
      stockChangeCount: dayEvents.filter((event) => eventKind(event) === "stock").length,
      infoChangeCount: dayEvents.filter((event) => eventKind(event) === "info").length,
    };
  });
}

function scanReliability(logs: ScanLog[]) {
  if (!logs.length) return 100;
  const successful = logs.filter((log) => log.status === "success").length;
  return Math.round((successful / logs.length) * 100);
}

function siteActivity(sites: Site[], events: ChangeEvent[]) {
  return sites.map((site) => ({
    site,
    events: events.filter((event) => event.site_id === site.id).length,
  })).sort((a, b) => b.events - a.events);
}

function totalFor(bucket: TrendBucket) {
  return bucket.newProductCount + bucket.priceChangeCount + bucket.stockChangeCount + bucket.infoChangeCount;
}

function maxTrendValue(buckets: TrendBucket[]) {
  return Math.max(1, ...buckets.map(totalFor));
}

function changeSummary(events: ChangeEvent[]) {
  return {
    newProductCount: events.filter((event) => eventKind(event) === "new").length,
    priceChangeCount: events.filter((event) => eventKind(event) === "price").length,
    stockChangeCount: events.filter((event) => eventKind(event) === "stock").length,
    infoChangeCount: events.filter((event) => eventKind(event) === "info").length,
  };
}

function normalizedInboxStatus(event: ChangeEvent) {
  const status = event.inbox_status || event.status || "unread";
  if (status === "reviewed" || status === "processed") return "read";
  if (status === "watched") return "important";
  return status;
}

function processingSummary(events: ChangeEvent[]) {
  const total = Math.max(1, events.length);
  const pendingCount = events.filter((event) => normalizedInboxStatus(event) === "unread").length;
  const followUpCount = events.filter((event) => ["important", "follow_up"].includes(normalizedInboxStatus(event))).length;
  const falsePositiveCount = events.filter((event) => normalizedInboxStatus(event) === "false_positive").length;
  const falsePositiveRate = Math.round((falsePositiveCount / total) * 100);
  return { pendingCount, followUpCount, falsePositiveCount, falsePositiveRate };
}

function assigneeWorkload(events: ChangeEvent[]) {
  const workload = new Map<string, number>();
  for (const event of events) {
    const assignee = event.assignee || "未指派";
    workload.set(assignee, (workload.get(assignee) || 0) + 1);
  }
  return Array.from(workload.entries())
    .map(([assignee, count]) => ({ assignee, count }))
    .sort((a, b) => b.count - a.count);
}

export function ReportsPage() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = () => {
    setLoading(true);
    loadOverview()
      .then(async (overview) => {
        const events = overview.live ? await loadChangeEvents().catch(() => overview.events) : overview.events;
        setData({ ...overview, events });
      })
      .finally(() => setLoading(false));
  };

  useEffect(refresh, []);

  const reports = useMemo(() => {
    const events = data?.events || [];
    const logs = data?.logs || [];
    return {
      summary: changeSummary(events),
      trendBars: buildTrendBuckets(events),
      siteActivity: siteActivity(data?.sites || [], events),
      scanReliability: scanReliability(logs),
      failedScans: logs.filter((log) => log.status && log.status !== "success").length,
      processingSummary: processingSummary(events),
      assigneeWorkload: assigneeWorkload(events),
    };
  }, [data]);

  if (loading || !data) {
    return <div className="page-loading"><RefreshCw size={18} className="spin" /> 正在生成报告与趋势...</div>;
  }

  const maxValue = maxTrendValue(reports.trendBars);

  return (
    <main className="reports-page">
      <header className="page-header">
        <div>
          <div className="eyebrow">REPORTS & TRENDS</div>
          <h1>报告与趋势</h1>
          <p>把新品上新、价格变化、库存变化、信息变化和抓取稳定性汇总成运营可读的趋势视图。</p>
          <div className={`api-status-pill ${data.live ? "success" : "warning"}`}>
            {data.live ? "真实 API" : "演示数据"} · {data.message}
          </div>
        </div>
        <div className="page-actions">
          <button className="icon-button" type="button" onClick={refresh} aria-label="刷新报告与趋势"><RefreshCw size={17} /></button>
          <button className="button button-secondary" type="button"><Download size={16} /> 导出报告</button>
          <Link className="primary-button" to="/monitors/new"><TrendingUp size={17} /> 新建监控</Link>
        </div>
      </header>

      <section className="report-summary-grid" aria-label="核心趋势指标">
        <ReportMetric label="新品上新" value={reports.summary.newProductCount} detail="最近事件总数" icon={<PackagePlus size={18} />} tone="blue" />
        <ReportMetric label="价格变化" value={reports.summary.priceChangeCount} detail="调价与促销变化" icon={<Tag size={18} />} tone="orange" />
        <ReportMetric label="库存变化" value={reports.summary.stockChangeCount} detail="补货、售罄和可售状态" icon={<Boxes size={18} />} tone="green" />
        <ReportMetric label="抓取成功率" value={`${reports.scanReliability}%`} detail={`${reports.failedScans} 条异常扫描`} icon={<ShieldCheck size={18} />} tone="purple" />
      </section>

      <section className="report-summary-grid" aria-label="运营处理复盘">
        <ReportMetric label="待处理" value={reports.processingSummary.pendingCount} detail="需要运营确认的变化" icon={<Clock3 size={18} />} tone="orange" />
        <ReportMetric label="需跟进" value={reports.processingSummary.followUpCount} detail="重点关注或跟进状态" icon={<AlertTriangle size={18} />} tone="purple" />
        <ReportMetric label="误报率" value={`${reports.processingSummary.falsePositiveRate}%`} detail={`${reports.processingSummary.falsePositiveCount} 条误报`} icon={<ShieldCheck size={18} />} tone="green" />
        <ReportMetric label="负责人工作量" value={reports.assigneeWorkload.length} detail="当前参与处理的人数" icon={<BarChart3 size={18} />} tone="blue" />
      </section>

      <section className="reports-grid">
        <div className="panel trend-panel">
          <div className="panel-heading">
            <div>
              <div className="panel-kicker">TREND BARS</div>
              <h2>7 日变化趋势</h2>
            </div>
            <span className="tag">trendBars</span>
          </div>
          <div className="trend-bars">
            {reports.trendBars.map((bucket) => (
              <div className="trend-bar-item" key={bucket.label}>
                <div className="trend-stack" title={`${bucket.label}: ${totalFor(bucket)} 条变化`}>
                  <span className="trend-segment new" style={{ height: `${(bucket.newProductCount / maxValue) * 100}%` }} />
                  <span className="trend-segment price" style={{ height: `${(bucket.priceChangeCount / maxValue) * 100}%` }} />
                  <span className="trend-segment stock" style={{ height: `${(bucket.stockChangeCount / maxValue) * 100}%` }} />
                  <span className="trend-segment info" style={{ height: `${(bucket.infoChangeCount / maxValue) * 100}%` }} />
                </div>
                <strong>{totalFor(bucket)}</strong>
                <span>{bucket.label}</span>
              </div>
            ))}
          </div>
          <div className="trend-legend">
            <span><i className="new" />新品</span>
            <span><i className="price" />价格</span>
            <span><i className="stock" />库存</span>
            <span><i className="info" />信息</span>
          </div>
        </div>

        <aside className="panel site-activity-panel">
          <div className="panel-heading">
            <div>
              <div className="panel-kicker">SITE ACTIVITY</div>
              <h2>站点活跃度</h2>
            </div>
            <span className="tag">siteActivity</span>
          </div>
          <div className="site-activity-list">
            {reports.siteActivity.length ? reports.siteActivity.map(({ site, events }) => (
              <div className="site-activity-row" key={site.id}>
                <div>
                  <strong>{site.name || site.url}</strong>
                  <span>{site.url}</span>
                </div>
                <em>{events} 条</em>
              </div>
            )) : (
              <div className="empty-state compact">
                <div className="empty-icon"><Activity size={18} /></div>
                <p>暂无站点活跃数据</p>
              </div>
            )}
          </div>
        </aside>
      </section>

      <section className="panel assignee-workload-panel">
        <div className="panel-heading">
          <div>
            <div className="panel-kicker">ASSIGNEE WORKLOAD</div>
            <h2>负责人工作量</h2>
          </div>
          <span className="tag">assigneeWorkload</span>
        </div>
        <div className="site-activity-list">
          {reports.assigneeWorkload.length ? reports.assigneeWorkload.map(({ assignee, count }) => (
            <div className="site-activity-row" key={assignee}>
              <div>
                <strong>{assignee}</strong>
                <span>已分配处理记录</span>
              </div>
              <em>{count} 条</em>
            </div>
          )) : (
            <div className="empty-state compact">
              <div className="empty-icon"><BarChart3 size={18} /></div>
              <p>暂无负责人工作量数据</p>
            </div>
          )}
        </div>
      </section>

      <section className="reports-grid">
        <div className="panel reliability-panel">
          <div className="panel-heading">
            <div>
              <div className="panel-kicker">SCAN RELIABILITY</div>
              <h2>抓取稳定性</h2>
            </div>
            <span className="tag">scanReliability</span>
          </div>
          <div className="reliability-card">
            <div className="reliability-ring" style={{ ["--score" as string]: `${reports.scanReliability}%` }}>
              <strong>{reports.scanReliability}%</strong>
            </div>
            <div>
              <h3>抓取健康度</h3>
              <p>根据最近扫描日志计算成功率。异常扫描越多，说明站点反爬、网络、选择器或渲染策略需要优化。</p>
            </div>
          </div>
        </div>

        <div className="panel insight-panel">
          <div className="panel-heading">
            <div>
              <div className="panel-kicker">INSIGHTS</div>
              <h2>运营提示</h2>
            </div>
          </div>
          <div className="insight-list">
            <Insight icon={<PackagePlus size={15} />} title="新品上新" detail={`当前周期发现 ${reports.summary.newProductCount} 条新品事件，适合进入选品复盘。`} />
            <Insight icon={<Tag size={15} />} title="价格变化" detail={`当前周期发现 ${reports.summary.priceChangeCount} 条价格变化，可用于竞品调价监控。`} />
            <Insight icon={<AlertTriangle size={15} />} title="抓取异常" detail={`当前周期存在 ${reports.failedScans} 条异常扫描，需要优先检查失败站点。`} />
          </div>
        </div>
      </section>
    </main>
  );
}

function ReportMetric({ label, value, detail, icon, tone }: { label: string; value: string | number; detail: string; icon: React.ReactNode; tone: string }) {
  return (
    <div className="metric-card report-summary-card">
      <div className={`metric-icon ${tone}`}>{icon}</div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}

function Insight({ icon, title, detail }: { icon: React.ReactNode; title: string; detail: string }) {
  return (
    <div className="insight-row">
      <span>{icon}</span>
      <div>
        <strong>{title}</strong>
        <p>{detail}</p>
      </div>
    </div>
  );
}
