import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Database,
  HardDrive,
  ListChecks,
  RefreshCw,
  ServerCog,
  ShieldCheck,
  Wifi,
} from "lucide-react";
import { Link } from "react-router-dom";
import { loadOperationsContext, type OperationsContext, type OperationsSummary } from "../../api/operations";
import { loadOverview } from "../../api/overview";
import type { ScanLog, SystemHealth } from "../../types/api";

type OpsMode = "live" | "fallback";

function relativeTime(value?: string | null) {
  if (!value) return "未开始";
  const minutes = Math.max(1, Math.round((Date.now() - new Date(value).getTime()) / 60000));
  if (minutes < 60) return `${minutes} 分钟前`;
  if (minutes < 1440) return `${Math.round(minutes / 60)} 小时前`;
  return `${Math.round(minutes / 1440)} 天前`;
}

function statusText(status?: string | null) {
  if (status === "success" || status === "completed") return "成功";
  if (status === "failed" || status === "error") return "失败";
  if (status === "running" || status === "processing") return "运行中";
  if (status === "queued" || status === "pending") return "排队中";
  return status || "未知";
}

function summaryFromLogs(scanLogs: ScanLog[]): OperationsSummary {
  const successful = scanLogs.filter((log) => log.status === "success").length;
  const failedLogs = scanLogs.filter((log) => log.status !== "success");
  return {
    scans: {
      total: scanLogs.length,
      successful,
      failed: failedLogs.length,
      success_rate: scanLogs.length ? successful / scanLogs.length : null,
      average_duration_ms: null,
    },
    queue: { queued: 0, running: 0, failed: 0 },
    notifications: { pending: 0, sending: 0, failed: 0 },
    failure_categories: [],
  };
}

function queueSummary(scanJobs: Array<{ status?: string | null }>) {
  return {
    queued: scanJobs.filter((job) => job.status === "queued" || job.status === "pending").length,
    running: scanJobs.filter((job) => job.status === "running" || job.status === "processing").length,
    failed: scanJobs.filter((job) => job.status === "failed" || job.status === "error").length,
  };
}

function workerStatus(health: SystemHealth) {
  return health.background_workers_enabled ? "后台 worker 已启用" : "后台 worker 未启用";
}

function schedulerStatus(health: SystemHealth) {
  const scheduler = health.scheduler;
  if (!scheduler?.required) return "当前环境不需要调度器";
  if (!scheduler.last_seen_at) return "尚未收到心跳";
  return scheduler.healthy ? `正常 · ${relativeTime(scheduler.last_seen_at)}` : `心跳超时 · ${relativeTime(scheduler.last_seen_at)}`;
}

function notificationWorkerStatus(health: SystemHealth) {
  return health.notification_worker_enabled ? "通知 worker 已启用" : "通知 worker 未启用";
}

function databaseStatus(health: SystemHealth) {
  return health.database_backend || "unknown";
}

function redisStatus(health: SystemHealth) {
  if (health.queue_backend === "rq") return health.redis_configured ? "Redis 已配置" : "Redis 未配置";
  return "当前队列不依赖 Redis";
}

function demoContextFromOverview(health: SystemHealth, logs: ScanLog[]): OperationsContext {
  const scanJobs = logs.slice(0, 6).map((log, index) => ({
    id: index + 1,
    site_id: log.site_id,
    site_name: log.site_name,
    job_type: "site_scan",
    trigger_type: index % 2 === 0 ? "scheduled" : "manual",
    status: log.status === "success" ? "completed" : "failed",
    queued_at: log.started_at,
    started_at: log.started_at,
    finished_at: log.finished_at,
    error_message: log.error_message,
  }));
  const summary = { ...summaryFromLogs(logs), queue: queueSummary(scanJobs) };
  return {
    health,
    scanLogs: logs,
    summary,
    scanJobs,
  };
}

export function OperationsPage() {
  const [context, setContext] = useState<OperationsContext | null>(null);
  const [mode, setMode] = useState<OpsMode>("live");
  const [message, setMessage] = useState("真实 API 已连接，当前展示后端运维数据");
  const [loading, setLoading] = useState(true);

  const refresh = () => {
    setLoading(true);
    loadOperationsContext()
      .then((nextContext) => {
        setContext(nextContext);
        setMode("live");
        setMessage("真实 API 已连接，当前展示后端运维数据");
      })
      .catch(async () => {
        const overview = await loadOverview();
        setContext(demoContextFromOverview(overview.health, overview.logs));
        setMode("fallback");
        setMessage("运维 API 不可用，当前显示演示/概览派生数据");
      })
      .finally(() => setLoading(false));
  };

  useEffect(refresh, []);

  const ops = useMemo(() => {
    const systemHealth = context?.health || { ok: false };
    const scanJobs = context?.scanJobs || [];
    const scanLogs = context?.scanLogs || [];
    const summary = context?.summary || summaryFromLogs(scanLogs);
    return {
      systemHealth,
      scanJobs,
      scanLogs,
      queueStatus: summary.queue,
      notificationStatus: summary.notifications,
      observability: summary,
      workerStatus: workerStatus(systemHealth),
      notificationWorkerStatus: notificationWorkerStatus(systemHealth),
      databaseStatus: databaseStatus(systemHealth),
      redisStatus: redisStatus(systemHealth),
      scanReliability: summary.scans.success_rate === null ? 100 : Math.round(summary.scans.success_rate * 100),
      failedLogs: scanLogs.filter((log) => log.status && log.status !== "success"),
      qualityBenchmark: context?.qualityBenchmark,
      realSiteBenchmark: context?.realSiteBenchmark,
    };
  }, [context]);

  if (loading || !context) {
    return <div className="page-loading"><RefreshCw size={18} className="spin" /> 正在同步运维中心...</div>;
  }

  return (
    <main className="operations-page">
      <header className="page-header">
        <div>
          <div className="eyebrow">OPERATIONS CENTER</div>
          <h1>运维中心</h1>
          <p>集中查看系统健康、队列状态、扫描任务、失败日志、数据库/Redis 和后台 worker 状态。</p>
          <div className={`api-status-pill ${mode === "live" ? "success" : "warning"}`}>
            {mode === "live" ? "真实 API" : "演示数据"} · {message}
          </div>
        </div>
        <div className="page-actions">
          <button className="icon-button" type="button" onClick={refresh} aria-label="刷新运维中心"><RefreshCw size={17} /></button>
          <Link className="primary-button" to="/monitors"><ServerCog size={17} /> 查看监控</Link>
        </div>
      </header>

      <section className="operations-summary-grid" aria-label="运维摘要">
        <OpsMetric label="系统健康" value={ops.systemHealth.ok ? "正常" : "异常"} detail="systemHealth" icon={<ShieldCheck size={18} />} tone="green" />
        <OpsMetric label="队列积压" value={ops.queueStatus.queued} detail={`运行中 ${ops.queueStatus.running} / 失败 ${ops.queueStatus.failed}`} icon={<ListChecks size={18} />} tone="blue" />
        <OpsMetric label="抓取成功率" value={`${ops.scanReliability}%`} detail={`${ops.observability.scans.total} 条扫描 / 平均 ${ops.observability.scans.average_duration_ms ?? "-"}ms`} icon={<Activity size={18} />} tone="orange" />
        <OpsMetric label="通知失败" value={ops.notificationStatus.failed} detail={`待发送 ${ops.notificationStatus.pending} / 发送中 ${ops.notificationStatus.sending}`} icon={<AlertTriangle size={18} />} tone="purple" />
        <OpsMetric label="数据库" value={ops.databaseStatus} detail="databaseStatus" icon={<Database size={18} />} tone="purple" />
      </section>

      {ops.qualityBenchmark ? (
        <section className="panel benchmark-panel" aria-label="抓取准确性基准">
          <div className="panel-heading">
            <div><div className="panel-kicker">EXTRACTION QUALITY</div><h2>抓取准确性基准</h2></div>
            <span className={`ops-status ${ops.qualityBenchmark.passed ? "success" : "failed"}`}>{ops.qualityBenchmark.passed ? "受控样本通过" : "需要修复"}</span>
          </div>
          <div className="benchmark-body">
            <div className="benchmark-intro"><strong>{ops.qualityBenchmark.case_count} 个受控样本</strong><span>{ops.qualityBenchmark.coverage.join(" · ")}</span><p>{ops.qualityBenchmark.limitation}</p></div>
            <div className="benchmark-fields">{Object.entries(ops.qualityBenchmark.field_pass_rates).map(([field, rate]) => <div key={field}><span>{benchmarkFieldLabel(field)}</span><strong>{Math.round(rate * 100)}%</strong></div>)}</div>
            <small>下一阶段需要接入人工标注的真实站点真值集，才可对外宣称实际抓取准确率。</small>
          </div>
        </section>
      ) : null}

      {ops.realSiteBenchmark ? (
        <section className="panel real-site-benchmark-panel" aria-label="真实站点基准">
          <div className="panel-heading">
            <div><div className="panel-kicker">REAL SITE REFERENCE</div><h2>真实站点基准</h2></div>
            <span className="ops-status queued">人工确认中</span>
          </div>
          <div className="real-site-summary">
            <strong>{ops.realSiteBenchmark.core_site_count} 个核心站点</strong>
            <span>已取得公开目录参考数：{ops.realSiteBenchmark.public_catalog_reference_count} 个</span>
            <small>{ops.realSiteBenchmark.next_action}</small>
          </div>
          <div className="real-site-list">
            {ops.realSiteBenchmark.sites.map((site) => (
              <article key={site.slug} className="real-site-row">
                <div><strong>{site.name}</strong><span>{site.platform_hint} · {site.is_control ? "活动页对照样本" : referenceStateLabel(site.reference_state)}</span></div>
                <div><b>{site.reference_count ?? "—"}</b><small>{site.reference_count === null ? "待人工确认" : "当前公开参考数"}</small></div>
                <p>{site.evidence}</p>
                <a href={site.url} target="_blank" rel="noreferrer">打开官网</a>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      <section className="operations-grid">
        <div className="panel ops-health-panel">
          <div className="panel-heading">
            <div>
              <div className="panel-kicker">RUNTIME</div>
              <h2>运行时健康</h2>
            </div>
            <span className="tag">workerStatus</span>
          </div>
          <div className="ops-health-list">
            <HealthRow icon={<ServerCog size={16} />} label="后台 worker（配置）" value={ops.workerStatus} ok={!!ops.systemHealth.background_workers_enabled} />
            <HealthRow icon={<Clock3 size={16} />} label="定时扫描调度器" value={schedulerStatus(ops.systemHealth)} ok={ops.systemHealth.scheduler?.healthy !== false} />
            <HealthRow icon={<Wifi size={16} />} label="通知 worker" value={ops.notificationWorkerStatus} ok={!!ops.systemHealth.notification_worker_enabled} />
            <HealthRow icon={<ListChecks size={16} />} label="队列后端" value={ops.systemHealth.queue_backend || "unknown"} ok={!!ops.systemHealth.queue_backend} />
            <HealthRow icon={<HardDrive size={16} />} label="Redis" value={ops.redisStatus} ok={ops.redisStatus !== "Redis 未配置"} />
            <HealthRow icon={<Database size={16} />} label="SQLite 路径" value={ops.systemHealth.sqlite_path || "未使用 SQLite"} ok />
          </div>
        </div>

        <aside className="panel ops-failures-panel">
          <div className="panel-heading">
            <div>
              <div className="panel-kicker">FAILURES</div>
              <h2>失败日志</h2>
            </div>
            <span className="tag">{ops.failedLogs.length} 条</span>
          </div>
          <div className="ops-failure-list">
            {ops.observability.failure_categories.length ? <div className="failure-category-list">{ops.observability.failure_categories.map((item) => <span className="tag" key={item.category}>{item.category} {item.count}</span>)}</div> : null}
            {ops.failedLogs.length ? ops.failedLogs.slice(0, 6).map((log) => (
              <article className="ops-failure-row" key={log.id}>
                <AlertTriangle size={16} />
                <div>
                  <strong>{log.site_name || `站点 #${log.site_id}`}</strong>
                  <span>{log.error_message || log.message || statusText(log.status)}</span>
                </div>
                <em>{relativeTime(log.started_at)}</em>
              </article>
            )) : (
              <div className="empty-state compact">
                <div className="empty-icon"><CheckCircle2 size={18} /></div>
                <p>当前没有失败扫描日志</p>
              </div>
            )}
          </div>
        </aside>
      </section>

      <section className="panel scan-jobs-panel">
        <div className="panel-heading">
          <div>
            <div className="panel-kicker">SCAN JOBS</div>
            <h2>扫描任务</h2>
          </div>
          <span className="tag">scanJobs</span>
        </div>
        {ops.scanJobs.length ? (
          <div className="ops-table-wrap">
            <table className="ops-table">
              <thead>
                <tr>
                  <th>任务</th>
                  <th>站点</th>
                  <th>触发</th>
                  <th>状态</th>
                  <th>候选</th>
                  <th>新增</th>
                  <th>时间</th>
                </tr>
              </thead>
              <tbody>
                {ops.scanJobs.slice(0, 20).map((job) => (
                  <tr key={job.id}>
                    <td><strong>#{job.id}</strong><span className="table-sub">{job.job_type || "scan"}</span></td>
                    <td>{job.site_name || `站点 #${job.site_id}`}<span className="table-sub">{job.source_url || job.source_type || "全站"}</span></td>
                    <td>{job.trigger_type || "manual"}</td>
                    <td><span className={`ops-status ${job.status || "unknown"}`}>{statusText(job.status)}</span>{job.error_message ? <span className="table-sub error-text">{job.error_message}</span> : null}</td>
                    <td>{job.candidates_count ?? 0}</td>
                    <td>{job.new_count ?? 0}</td>
                    <td><span className="time-cell"><Clock3 size={13} />{relativeTime(job.queued_at || job.started_at)}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            <div className="empty-icon"><ListChecks size={20} /></div>
            <h3>暂无扫描任务</h3>
            <p>触发站点扫描后，任务会显示在这里。</p>
          </div>
        )}
      </section>
    </main>
  );
}

function benchmarkFieldLabel(field: string) {
  return ({ url: "商品链接", title: "标题", price_amount: "价格", currency: "币种", availability: "库存", variant_count: "变体数" } as Record<string, string>)[field] || field;
}

function referenceStateLabel(state: string) {
  return ({ public_catalog_count: "公开目录已核对", sitemap_candidates: "Sitemap 候选待确认", manual_required: "需人工确认", negative_control: "对照样本" } as Record<string, string>)[state] || state;
}

function OpsMetric({ label, value, detail, icon, tone }: { label: string; value: string | number; detail: string; icon: React.ReactNode; tone: string }) {
  return (
    <div className="metric-card operations-summary-card">
      <div className={`metric-icon ${tone}`}>{icon}</div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}

function HealthRow({ icon, label, value, ok }: { icon: React.ReactNode; label: string; value: string; ok: boolean }) {
  return (
    <div className={`ops-health-row ${ok ? "ok" : "warning"}`}>
      <span>{icon}</span>
      <div>
        <strong>{label}</strong>
        <small>{value}</small>
      </div>
      <em>{ok ? "正常" : "注意"}</em>
    </div>
  );
}
