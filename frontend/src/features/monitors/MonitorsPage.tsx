import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  Clock3,
  Edit3,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Zap,
} from "lucide-react";
import { Link } from "react-router-dom";
import { ApiError } from "../../api/client";
import { triggerSiteScan, updateSiteEnabled } from "../../api/monitors";
import { loadOverview, type OverviewData } from "../../api/overview";

type MonitorStatus = "healthy" | "warning" | "paused";

type MonitorRow = {
  id: number;
  name: string;
  url: string;
  type: string;
  status: MonitorStatus;
  lastScan: string;
  successRate: number;
  changesToday: number;
  failureReason: string;
  frequency: string;
};

type ActionState = {
  id: number | null;
  kind: "scan" | "toggle" | null;
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
};

function relativeTime(value?: string | null) {
  if (!value) return "尚未扫描";
  const minutes = Math.max(1, Math.round((Date.now() - new Date(value).getTime()) / 60000));
  if (minutes < 60) return `${minutes} 分钟前`;
  if (minutes < 1440) return `${Math.round(minutes / 60)} 小时前`;
  return `${Math.round(minutes / 1440)} 天前`;
}

function buildMonitorRows(data: OverviewData): MonitorRow[] {
  return data.sites.map((site) => {
    const siteLogs = data.logs.filter((log) => log.site_id === site.id);
    const latestLog = siteLogs[0];
    const successfulScans = siteLogs.filter((log) => log.status === "success").length;
    const successRate = siteLogs.length ? Math.round((successfulScans / siteLogs.length) * 100) : 100;
    const changesToday = data.events.filter((event) => event.site_id === site.id && event.status !== "reviewed").length;
    const sourceType = site.sources?.[0]?.source_type || "collection";
    const status: MonitorStatus = site.enabled === false ? "paused" : latestLog?.status === "warning" || latestLog?.status === "failed" ? "warning" : "healthy";

    return {
      id: site.id,
      name: site.name,
      url: site.url,
      type: monitorTypeBySource[sourceType] || "页面变化",
      status,
      lastScan: relativeTime(latestLog?.started_at),
      successRate,
      changesToday,
      failureReason: latestLog?.error_message || "无异常",
      frequency: site.scan_interval_minutes ? `${site.scan_interval_minutes} 分钟` : "每 60 分钟",
    };
  });
}

function summarize(rows: MonitorRow[]) {
  const active = rows.filter((row) => row.status !== "paused").length;
  const warning = rows.filter((row) => row.status === "warning").length;
  const changes = rows.reduce((total, row) => total + row.changesToday, 0);
  const averageRate = rows.length ? Math.round(rows.reduce((total, row) => total + row.successRate, 0) / rows.length) : 100;
  return { active, warning, changes, averageRate };
}

export function MonitorsPage() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState<ActionState>({ id: null, kind: null, message: "", tone: "idle" });

  const refresh = () => {
    setLoading(true);
    loadOverview().then(setData).finally(() => setLoading(false));
  };

  useEffect(refresh, []);

  const rows = useMemo(() => (data ? buildMonitorRows(data) : []), [data]);
  const stats = useMemo(() => summarize(rows), [rows]);

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

  if (loading || !data) {
    return <div className="page-loading"><RefreshCw size={18} className="spin" /> 正在同步监控任务…</div>;
  }

  return (
    <main className="monitors-page">
      <header className="page-header">
        <div>
          <div className="eyebrow">MONITOR CENTER</div>
          <h1>监控中心</h1>
          <p>集中管理官网、集合页和商品页的新品上新、价格、库存与内容变化监控。</p>
        </div>
        <div className="page-actions">
          <button className="icon-button" type="button" onClick={refresh} aria-label="刷新监控中心">
            <RefreshCw size={17} />
          </button>
          <Link className="primary-button" to="/monitors/new"><Plus size={17} /> 新建监控</Link>
        </div>
      </header>

      <section className="monitor-summary-grid" aria-label="监控概览">
        <SummaryCard label="活跃监控" value={stats.active} detail="正在按计划扫描" icon={<ShieldCheck size={18} />} tone="blue" />
        <SummaryCard label="待处理变化" value={stats.changes} detail="新品、价格或库存变化" icon={<Zap size={18} />} tone="purple" />
        <SummaryCard label="需要关注" value={stats.warning} detail="失败或响应偏慢" icon={<AlertTriangle size={18} />} tone="orange" />
        <SummaryCard label="平均成功率" value={`${stats.averageRate}%`} detail="最近扫描表现" icon={<CheckCircle2 size={18} />} tone="green" />
      </section>

      <section className="panel monitor-toolbar" aria-label="监控筛选">
        <div className="monitor-search">
          <Search size={15} aria-hidden="true" />
          <input type="search" placeholder="搜索品牌、站点或目标 URL" aria-label="搜索品牌、站点或目标 URL" />
        </div>
        <button className="button button-secondary" type="button">
          <SlidersHorizontal size={15} aria-hidden="true" />
          <span>筛选</span>
        </button>
        <button className="button button-secondary" type="button">
          <Play size={15} aria-hidden="true" />
          <span>批量扫描</span>
        </button>
      </section>

      {action.message ? <div className={`operation-message ${action.tone}`} role="status">{action.message}</div> : null}

      <section className="panel monitors-table-panel">
        <div className="panel-heading">
          <div>
            <div className="panel-kicker">TASKS</div>
            <h2>全部监控任务</h2>
          </div>
          <span className="monitor-count">{rows.length} 个任务</span>
        </div>

        {rows.length === 0 ? (
          <EmptyMonitors />
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
                  <th>今日变化</th>
                  <th>失败原因</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <MonitorTableRow key={row.id} row={row} action={action} onScan={runScan} onToggle={toggleEnabled} />
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

function MonitorTableRow({ row, action, onScan, onToggle }: { row: MonitorRow; action: ActionState; onScan: (row: MonitorRow) => void; onToggle: (row: MonitorRow) => void }) {
  const scanning = action.id === row.id && action.kind === "scan";
  const toggling = action.id === row.id && action.kind === "toggle";
  const paused = row.status === "paused";

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
      <td><span className={`monitor-status ${row.status}`}><span className={`status-dot ${row.status === "warning" ? "warning" : "success"}`} />{statusText[row.status]}</span></td>
      <td><span className="time-cell"><Clock3 size={14} />{row.lastScan}</span><span className="table-sub">{row.frequency}</span></td>
      <td><strong>{row.successRate}%</strong></td>
      <td><span className={row.changesToday ? "change-count active" : "change-count"}>{row.changesToday}</span></td>
      <td><span className={row.status === "warning" ? "failure-text warning" : "failure-text"}>{row.failureReason}</span></td>
      <td>
        <div className="monitor-actions">
          <button className="icon-action" type="button" aria-label={`${row.name} 立即扫描`} title="立即扫描" onClick={() => onScan(row)} disabled={scanning || toggling}><RefreshCw size={14} /></button>
          <button className="icon-action" type="button" aria-label={`${row.name} ${paused ? "恢复" : "暂停"}`} title={paused ? "恢复" : "暂停"} onClick={() => onToggle(row)} disabled={scanning || toggling}>{paused ? <Play size={14} /> : <Pause size={14} />}</button>
          <Link className="icon-action" to={`/monitors/${row.id}`} aria-label={`${row.name} 编辑规则`} title="编辑规则"><Edit3 size={14} /></Link>
          <Link className="icon-action" to="/inbox" aria-label={`${row.name} 查看变化`} title="查看变化"><ArrowUpRight size={14} /></Link>
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
