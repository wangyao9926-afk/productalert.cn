import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Edit3,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { Link } from "react-router-dom";
import { ApiError } from "../../api/client";
import { deleteSite, getSiteBaselineSummary, triggerSiteScan, updateSiteEnabled, type ScanQuality, type SiteBaselineSummary } from "../../api/monitors";
import { loadOverview, type OverviewData } from "../../api/overview";

type MonitorStatus = "healthy" | "warning" | "paused" | "pending";
type CatalogState = "ready" | "warning" | "pending";

type MonitorRow = {
  id: number;
  name: string;
  url: string;
  type: string;
  status: MonitorStatus;
  lastScan: string;
  successRate: number;
  scanHealth: "healthy" | "warning";
  catalogState: CatalogState;
  catalogLabel: string;
  catalogDetail: string;
  catalogHref: string;
  catalogTitle: string;
  failureReason: string;
  frequency: string;
};

type ActionState = {
  id: number | null;
  kind: "scan" | "toggle" | "delete" | null;
  message: string;
  tone: "success" | "error" | "idle";
};

const monitorTypeBySource: Record<string, string> = {
  sitemap: "新品上新",
  collection: "商品列表",
  rendered: "动态页面",
  product: "价格库存",
};

const statusText: Record<MonitorStatus, string> = {
  healthy: "正常",
  warning: "需关注",
  paused: "已暂停",
  pending: "待建立基线",
};

function relativeTime(value?: string | null) {
  if (!value) return "尚未扫描";
  const minutes = Math.max(1, Math.round((Date.now() - new Date(value).getTime()) / 60000));
  if (minutes < 60) return `${minutes} 分钟前`;
  if (minutes < 1440) return `${Math.round(minutes / 60)} 小时前`;
  return `${Math.round(minutes / 1440)} 天前`;
}

function scanFailureReason(latestLog: OverviewData["logs"][number] | undefined, successRate: number, scanCount: number) {
  if (latestLog?.error_message) return latestLog.error_message;
  if (latestLog?.status === "failed") return "最近一次扫描失败，但未返回具体错误";
  if (latestLog?.status === "warning") return "最近一次扫描需要人工检查";
  if (scanCount >= 2 && successRate < 80) return `最近 ${scanCount} 次扫描成功率仅 ${successRate}%`;
  return "无异常";
}

function catalogIssueSummary(quality: ScanQuality | undefined) {
  const issues: string[] = [];
  if (quality?.rate_limited_count) issues.push(`限流 ${quality.rate_limited_count}`);
  if (quality?.blocked_count) issues.push(`访问受限 ${quality.blocked_count}`);
  if (quality?.fetch_failed_count) issues.push(`读取失败 ${quality.fetch_failed_count}`);
  if (quality?.parse_failed_count) issues.push(`解析失败 ${quality.parse_failed_count}`);
  if (quality?.pending_retry_count) issues.push(`待重试 ${quality.pending_retry_count}`);
  return issues.join("，");
}

function catalogBaseline(summary: SiteBaselineSummary | undefined): Pick<MonitorRow, "catalogState" | "catalogLabel" | "catalogDetail" | "catalogHref" | "catalogTitle"> {
  if (!summary) {
    return { catalogState: "ready", catalogLabel: "基线状态待同步", catalogDetail: "暂未取得本次扫描证据", catalogHref: "/products", catalogTitle: "打开产品库" };
  }

  const latestJob = summary.latest_job;
  const progress = latestJob?.result?.progress;
  const quality = progress?.quality;
  const productCount = summary.product_count || 0;
  const waitingForScan = latestJob?.status === "queued" || latestJob?.status === "running" || (!latestJob && productCount === 0);
  const productHref = `/products?site_id=${summary.site_id}`;
  const evidenceHref = latestJob ? `/monitors/${summary.site_id}/baseline/${latestJob.id}` : productHref;
  const issues = catalogIssueSummary(quality);

  if (waitingForScan) {
    return { catalogState: "pending", catalogLabel: "待建立基线", catalogDetail: "首次扫描后统计商品数量", catalogHref: evidenceHref, catalogTitle: "查看扫描进度" };
  }
  if (summary.baseline_completed && productCount > 0) {
    const referenceCount = quality?.catalog_reference_count;
    if (quality?.coverage_state === "verified") {
      return { catalogState: "ready", catalogLabel: `${productCount} 个商品`, catalogDetail: `目录已核验：${productCount} / ${referenceCount ?? productCount}`, catalogHref: productHref, catalogTitle: "查看产品库" };
    }
    if (quality?.coverage_state === "incomplete" || quality?.coverage_state === "failed") {
      return { catalogState: "warning", catalogLabel: `${productCount} 个商品`, catalogDetail: `目录不完整：${issues || "需要继续扫描"}`, catalogHref: evidenceHref, catalogTitle: "查看扫描证据并继续扫描" };
    }
    return { catalogState: "warning", catalogLabel: `${productCount} 个商品`, catalogDetail: "目录数量待核验：未取得公开目录参考", catalogHref: evidenceHref, catalogTitle: "查看扫描证据" };
  }
  if (productCount === 0) {
    const cause = latestJob?.message || (quality?.rate_limited_count ? "官网限流，等待重试" : "未发现可验证的商品页");
    return { catalogState: "warning", catalogLabel: "未建立商品基线", catalogDetail: cause, catalogHref: evidenceHref, catalogTitle: "查看扫描证据并重新扫描" };
  }
  return { catalogState: "warning", catalogLabel: `${productCount} 个商品`, catalogDetail: `目录不完整：${issues || "本次扫描尚未完成"}`, catalogHref: evidenceHref, catalogTitle: "查看扫描证据并继续扫描" };
}

function buildMonitorRows(data: OverviewData, baselineBySite: Record<number, SiteBaselineSummary | undefined>): MonitorRow[] {
  return data.sites.map((site) => {
    const siteLogs = data.logs.filter((log) => log.site_id === site.id);
    const latestLog = siteLogs[0];
    const successfulScans = siteLogs.filter((log) => log.status === "success").length;
    const successRate = siteLogs.length ? Math.round((successfulScans / siteLogs.length) * 100) : 100;
    const sourceType = site.sources?.[0]?.source_type || "collection";
    const lowSuccessRate = siteLogs.length >= 2 && successRate < 80;
    const scanHealth = latestLog?.status === "warning" || latestLog?.status === "failed" || lowSuccessRate ? "warning" : "healthy";
    const catalog = catalogBaseline(baselineBySite[site.id]);
    const status: MonitorStatus = site.enabled === false ? "paused" : catalog.catalogState === "pending" ? "pending" : scanHealth === "warning" || catalog.catalogState === "warning" ? "warning" : "healthy";

    return {
      id: site.id,
      name: site.name,
      url: site.url,
      type: monitorTypeBySource[sourceType] || "页面变化",
      status,
      lastScan: relativeTime(latestLog?.started_at),
      successRate,
      scanHealth,
      catalogState: catalog.catalogState,
      catalogLabel: catalog.catalogLabel,
      catalogDetail: catalog.catalogDetail,
      catalogHref: catalog.catalogHref,
      catalogTitle: catalog.catalogTitle,
      failureReason: scanHealth === "warning" ? scanFailureReason(latestLog, successRate, siteLogs.length) : catalog.catalogState === "warning" ? catalog.catalogDetail : "无异常",
      frequency: site.scan_interval_minutes ? `${site.scan_interval_minutes} 分钟` : "每 60 分钟",
    };
  });
}

function summarize(rows: MonitorRow[]) {
  const active = rows.filter((row) => row.status === "healthy" || row.status === "warning").length;
  const warning = rows.filter((row) => row.status === "warning").length;
  const pausedCount = rows.filter((row) => row.status === "paused").length;
  const averageRate = rows.length ? Math.round(rows.reduce((total, row) => total + row.successRate, 0) / rows.length) : 100;
  return { active, warning, pausedCount, averageRate };
}

export function MonitorsPage() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [baselineBySite, setBaselineBySite] = useState<Record<number, SiteBaselineSummary | undefined>>({});
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<MonitorStatus | "all">("all");
  const [action, setAction] = useState<ActionState>({ id: null, kind: null, message: "", tone: "idle" });

  const refresh = async () => {
    setLoading(true);
    try {
      const overview = await loadOverview();
      setData(overview);
      const summaries = await Promise.all(overview.sites.map(async (site) => [site.id, await getSiteBaselineSummary(site.id).catch(() => undefined)] as const));
      setBaselineBySite(Object.fromEntries(summaries));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const rows = useMemo(() => (data ? buildMonitorRows(data, baselineBySite) : []), [baselineBySite, data]);
  const stats = useMemo(() => summarize(rows), [rows]);
  const filteredRows = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return rows.filter((row) => {
      const queryMatch = !normalizedQuery || `${row.name} ${row.url} ${row.type}`.toLowerCase().includes(normalizedQuery);
      const statusMatch = statusFilter === "all" || row.status === statusFilter;
      return queryMatch && statusMatch;
    });
  }, [query, rows, statusFilter]);

  const actionErrorMessage = (error: unknown) => {
    if (error instanceof ApiError && error.status === 401) return "请先登录 ProductAlert API，再执行监控操作。";
    if (error instanceof ApiError) {
      try {
        const parsed = JSON.parse(error.body) as { detail?: string };
        return parsed.detail || `操作失败：API 返回 ${error.status}`;
      } catch {
        return error.body || `操作失败：API 返回 ${error.status}`;
      }
    }
    return "操作失败：API 不可用，请确认后端服务已启动。";
  };

  const runScan = async (row: MonitorRow) => {
    setAction({ id: row.id, kind: "scan", message: "", tone: "idle" });
    try {
      const job = await triggerSiteScan(row.id);
      setAction({ id: row.id, kind: null, message: `操作成功：已提交立即扫描${job.id ? `，任务 #${job.id}` : ""}。`, tone: "success" });
      refresh();
    } catch (error) {
      setAction({ id: row.id, kind: null, message: actionErrorMessage(error), tone: "error" });
    }
  };

  const toggleEnabled = async (row: MonitorRow) => {
    const enabled = row.status === "paused";
    setAction({ id: row.id, kind: "toggle", message: "", tone: "idle" });
    try {
      await updateSiteEnabled(row.id, enabled);
      setAction({ id: row.id, kind: null, message: `操作成功：已${enabled ? "恢复" : "暂停"} ${row.name}。`, tone: "success" });
      refresh();
    } catch (error) {
      setAction({ id: row.id, kind: null, message: actionErrorMessage(error), tone: "error" });
    }
  };

  const removeMonitor = async (row: MonitorRow) => {
    const confirmed = window.confirm(`删除监控“${row.name}”？此操作会一并删除产品、扫描记录和变化记录，且无法恢复。`);
    if (!confirmed) return;
    setAction({ id: row.id, kind: "delete", message: "", tone: "idle" });
    try {
      await deleteSite(row.id);
      setAction({ id: null, kind: null, message: `已删除监控：${row.name}。`, tone: "success" });
      refresh();
    } catch (error) {
      setAction({ id: row.id, kind: null, message: actionErrorMessage(error), tone: "error" });
    }
  };

  if (loading || !data) {
    return <div className="page-loading"><RefreshCw size={18} className="spin" /> 正在同步监控任务…</div>;
  }

  return (
    <main className="monitors-page">
      <header className="page-header">
        <div>
          <div className="eyebrow">MONITOR CENTER</div>
          <h1>监控中心</h1>
          <p>查看官网采集是否正常、手动扫描、调整频率或处理失败；需要判断的商业变化在情报收件箱处理。</p>
        </div>
        <div className="page-actions">
          <button className="icon-button" type="button" onClick={refresh} aria-label="刷新监控中心">
            <RefreshCw size={17} />
          </button>
          <Link className="primary-button" to="/monitors/new"><Plus size={17} /> 新建监控</Link>
        </div>
      </header>

      <section className="monitor-summary-grid" aria-label="监控概览">
        <SummaryCard label="监控运行状态" value={stats.active} detail="正在按计划扫描" icon={<ShieldCheck size={18} />} tone="blue" />
        <SummaryCard label="采集异常" value={stats.warning} detail="失败、限流或解析异常" icon={<AlertTriangle size={18} />} tone="orange" />
        <SummaryCard label="已暂停" value={stats.pausedCount} detail="暂不执行自动扫描" icon={<Pause size={18} />} tone="purple" />
        <SummaryCard label="平均成功率" value={`${stats.averageRate}%`} detail="最近扫描表现" icon={<CheckCircle2 size={18} />} tone="green" />
      </section>

      <section className="panel monitor-toolbar" aria-label="监控筛选">
        <div className="monitor-search">
          <Search size={15} aria-hidden="true" />
          <input value={query} onChange={(event) => setQuery(event.target.value)} type="search" placeholder="搜索监控：站点名称、URL 或类型" aria-label="搜索监控" />
        </div>
        <select className="select-input compact-select" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as MonitorStatus | "all")} aria-label="按状态筛选">
          <option value="all">全部状态</option>
          <option value="healthy">正常</option>
          <option value="warning">需关注</option>
          <option value="pending">待建立基线</option>
          <option value="paused">已暂停</option>
        </select>
        {(query || statusFilter !== "all") ? <button className="button button-secondary" type="button" onClick={() => { setQuery(""); setStatusFilter("all"); }}>清除筛选</button> : null}
      </section>

      {action.message ? <div className={`operation-message ${action.tone}`} role="status">{action.message}</div> : null}

      <section className="panel monitors-table-panel">
        <div className="panel-heading">
          <div>
            <div className="panel-kicker">MONITOR HEALTH</div>
            <h2>官网监控</h2>
          </div>
          <span className="monitor-count">{filteredRows.length === rows.length ? `${rows.length} 个站点` : `${filteredRows.length} / ${rows.length} 个站点`}</span>
        </div>

        {rows.length === 0 ? (
          <EmptyMonitors />
        ) : filteredRows.length === 0 ? (
          <div className="empty-state"><div className="empty-icon"><Search size={20} /></div><h3>暂无匹配的监控任务</h3><p>请清除搜索词或调整状态筛选。</p></div>
        ) : (
          <div className="monitors-table-wrap">
            <table className="monitors-table">
              <thead>
                <tr>
                  <th>监控目标</th>
                  <th>类型</th>
                  <th>状态</th>
                  <th>最近扫描</th>
                  <th>成功率</th>
                  <th>商品基线</th>
                  <th>采集说明</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row) => (
                  <MonitorTableRow key={row.id} row={row} action={action} onScan={runScan} onToggle={toggleEnabled} onDelete={removeMonitor} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}

function SummaryCard({ label, value, detail, icon, tone }: { label: string; value: string | number; detail: string; icon: React.ReactNode; tone: string }) {
  return (
    <div className="metric-card monitor-summary-card">
      <div className={`metric-icon ${tone}`}>{icon}</div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}

function MonitorTableRow({ row, action, onScan, onToggle, onDelete }: { row: MonitorRow; action: ActionState; onScan: (row: MonitorRow) => void; onToggle: (row: MonitorRow) => void; onDelete: (row: MonitorRow) => void }) {
  const scanning = action.id === row.id && action.kind === "scan";
  const toggling = action.id === row.id && action.kind === "toggle";
  const deleting = action.id === row.id && action.kind === "delete";
  const paused = row.status === "paused";
  const statusDot = row.status === "warning" ? "warning" : row.status === "healthy" ? "success" : "";

  return (
    <tr>
      <td>
        <div className="monitor-target">
          <span className="site-avatar">{row.name.slice(0, 1)}</span>
          <div>
            <strong>{row.name}</strong>
            <span>{row.url}</span>
          </div>
        </div>
      </td>
      <td><span className="tag">{row.type}</span></td>
      <td><span className={`monitor-status ${row.status}`}><span className={`status-dot ${statusDot}`} />{statusText[row.status]}</span></td>
      <td><span className="time-cell"><Clock3 size={14} />{row.lastScan}</span><span className="table-sub">{row.frequency}</span></td>
      <td><strong>{row.successRate}%</strong></td>
      <td>
        <Link className={`catalog-baseline ${row.catalogState}`} to={row.catalogHref} title={`${row.name}：${row.catalogTitle}`}>
          <strong>{row.catalogLabel}</strong>
          <span>{row.catalogDetail}</span>
        </Link>
      </td>
      <td><span className={row.status === "warning" ? "failure-text warning" : "failure-text"}>{row.failureReason}</span></td>
      <td>
        <div className="monitor-actions">
          <button className="icon-action" type="button" aria-label={`${row.name} 立即扫描`} title="立即扫描" onClick={() => onScan(row)} disabled={scanning || toggling || deleting}><RefreshCw size={14} /></button>
          <button className="icon-action" type="button" aria-label={`${row.name} ${paused ? "恢复" : "暂停"}`} title={paused ? "恢复" : "暂停"} onClick={() => onToggle(row)} disabled={scanning || toggling || deleting}>{paused ? <Play size={14} /> : <Pause size={14} />}</button>
          <Link className="icon-action" to={`/monitors/${row.id}`} aria-label={`${row.name} 编辑规则`} title="编辑规则"><Edit3 size={14} /></Link>
          <button className="icon-action danger-action" type="button" aria-label={`${row.name} 删除监控`} title="删除监控" onClick={() => onDelete(row)} disabled={scanning || toggling || deleting}><Trash2 size={14} /></button>
        </div>
      </td>
    </tr>
  );
}

function EmptyMonitors() {
  return (
    <div className="empty-state">
      <div className="empty-icon"><ShieldCheck size={20} /></div>
      <h3>还没有监控任务</h3>
      <p>先添加一个品牌官网或商品集合页，ProductAlert 会持续检测新品、价格和库存变化。</p>
      <Link className="primary-button" to="/monitors/new"><Plus size={17} /> 新建监控</Link>
    </div>
  );
}
