import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BellRing,
  CheckCircle2,
  Clock3,
  Download,
  Mail,
  MessageSquare,
  RefreshCw,
  RotateCcw,
  Send,
  Webhook,
} from "lucide-react";
import { Link } from "react-router-dom";
import { ApiError } from "../../api/client";
import { loadNotificationRules, loadNotifications, retryNotification, type NotificationRecord, type NotificationRule } from "../../api/notifications";
import { loadOverview, type OverviewData } from "../../api/overview";

const channelCards = [
  { label: "邮件", icon: Mail, detail: "适合日报、低频人工审阅、团队归档" },
  { label: "Webhook", icon: Webhook, detail: "适合对接内部系统、自动化任务和数据仓库" },
  { label: "企业微信 / 飞书", icon: MessageSquare, detail: "适合运营即时提醒、值班群和项目协同" },
];

const eventTypeLabels: Record<string, string> = {
  product_new: "新品上新",
  price_change: "价格变化",
  availability_change: "库存变化",
  description_change: "信息变化",
  text_change: "信息变化",
};

const severityLabels: Record<string, string> = {
  low: "低",
  normal: "普通",
  high: "高",
  critical: "紧急",
};

const inboxStatusLabels: Record<string, string> = {
  unread: "未读事件",
  important: "重点事件",
  read: "已读事件",
  false_positive: "误报事件",
  follow_up: "需跟进事件",
};

const channelLabels: Record<string, string> = {
  webhook: "Webhook",
  email: "邮件",
  wecom: "企业微信",
  feishu: "飞书",
};

const demoRules: NotificationRule[] = [
  {
    id: 1,
    name: "只推送新品/价格变化",
    channel: "webhook",
    target_url: "https://hooks.example.com/productalert",
    event_types: ["product_new", "price_change"],
    min_severity: "normal",
    inbox_status: "unread",
    enabled: true,
  },
  {
    id: 2,
    name: "只推送高严重程度",
    channel: "email",
    target_url: "ops@example.com",
    event_types: ["product_new", "price_change", "availability_change", "text_change"],
    min_severity: "high",
    inbox_status: "important",
    enabled: true,
  },
  {
    id: 3,
    name: "只推送需跟进事件",
    channel: "feishu",
    target_url: "feishu://productalert/ops",
    event_types: ["product_new", "price_change"],
    min_severity: "normal",
    inbox_status: "follow_up",
    enabled: false,
  },
];

function statusLabel(status?: string | null) {
  if (status === "sent") return "已发送";
  if (status === "failed") return "失败";
  if (status === "pending") return "待发送";
  if (status === "processing") return "发送中";
  return status || "未知";
}

function relativeTime(value?: string | null) {
  if (!value) return "刚刚";
  const minutes = Math.max(1, Math.round((Date.now() - new Date(value).getTime()) / 60000));
  if (minutes < 60) return `${minutes} 分钟前`;
  if (minutes < 1440) return `${Math.round(minutes / 60)} 小时前`;
  return `${Math.round(minutes / 1440)} 天前`;
}

function queueSummary(items: NotificationRecord[]) {
  return {
    pending: items.filter((item) => item.status === "pending").length,
    sent: items.filter((item) => item.status === "sent").length,
    failed: items.filter((item) => item.status === "failed").length,
    webhook: items.filter((item) => (item.channel || "").toLowerCase().includes("webhook")).length,
  };
}

function ruleSummary(rule: NotificationRule) {
  const types = rule.event_types.map((item) => eventTypeLabels[item] || item).join("、");
  return {
    types,
    severity: severityLabels[rule.min_severity] || rule.min_severity,
    status: inboxStatusLabels[rule.inbox_status] || rule.inbox_status,
    channel: channelLabels[rule.channel] || rule.channel,
  };
}

function demoNotifications(events: OverviewData["events"]): NotificationRecord[] {
  return events.slice(0, 4).map((event, index) => ({
    id: index + 1,
    site_id: event.site_id,
    site_name: event.site_name,
    product_title: event.product_title,
    product_url: event.product_url,
    event_id: event.id,
    event_summary: event.summary,
    change_type: event.change_type,
    channel: index % 2 === 0 ? "webhook" : "email",
    target_url: index % 2 === 0 ? "https://hooks.example.com/productalert" : "ops@example.com",
    status: index === 2 ? "failed" : index === 3 ? "pending" : "sent",
    attempts: index === 2 ? 3 : 1,
    created_at: event.created_at,
    last_error: index === 2 ? "Webhook 返回 500，等待重试" : null,
  }));
}

export function NotificationsPage() {
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [notifications, setNotifications] = useState<NotificationRecord[]>([]);
  const [rules, setRules] = useState<NotificationRule[]>(demoRules);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("all");
  const [updatingId, setUpdatingId] = useState<number | null>(null);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const refresh = () => {
    setLoading(true);
    setMessage(null);
    Promise.allSettled([loadOverview(), loadNotifications(), loadNotificationRules()])
      .then(([overviewResult, notificationResult, rulesResult]) => {
        const nextOverview = overviewResult.status === "fulfilled" ? overviewResult.value : null;
        setOverview(nextOverview);
        if (rulesResult.status === "fulfilled") {
          setRules(rulesResult.value.length ? rulesResult.value : demoRules);
        } else {
          setRules(demoRules);
        }
        if (notificationResult.status === "fulfilled") {
          setNotifications(notificationResult.value);
          return;
        }
        setNotifications(demoNotifications(nextOverview?.events || []));
      })
      .finally(() => setLoading(false));
  };

  useEffect(refresh, []);

  const live = !!overview?.live;
  const filtered = useMemo(() => {
    if (statusFilter === "all") return notifications;
    return notifications.filter((item) => item.status === statusFilter);
  }, [notifications, statusFilter]);
  const summary = queueSummary(notifications);

  const handleRetry = async (id: number) => {
    setUpdatingId(id);
    setMessage(null);
    try {
      const updated = await retryNotification(id);
      setNotifications((current) => current.map((item) => item.id === id ? { ...item, ...updated } : item));
      setMessage({ type: "success", text: "重试通知已提交，系统会重新发送该通知" });
    } catch (error) {
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
        setMessage({ type: "error", text: "请先登录后再重试通知" });
      } else {
        setMessage({ type: "error", text: "重试通知失败，请检查后端通知服务" });
      }
    } finally {
      setUpdatingId(null);
    }
  };

  if (loading) {
    return <div className="page-loading"><RefreshCw size={18} className="spin" /> 正在同步通知中心...</div>;
  }

  return (
    <main className="notifications-page">
      <header className="page-header">
        <div>
          <div className="eyebrow">NOTIFICATION CENTER</div>
          <h1>通知中心</h1>
          <p>集中管理新品上新、价格变化、库存变化和信息变化的通知队列与通知策略，按事件类型、严重程度和处理状态控制推送。</p>
          <div className={`api-status-pill ${live ? "success" : "warning"}`}>
            {live ? "真实 API" : "演示数据"} · {overview?.message || "通知 API 不可用，当前显示演示数据"}
          </div>
        </div>
        <div className="page-actions">
          <button className="icon-button" type="button" onClick={refresh} aria-label="刷新通知中心"><RefreshCw size={17} /></button>
          <a className="button button-secondary" href="/api/export/notifications.csv" target="_blank" rel="noreferrer"><Download size={16} /> 导出 CSV</a>
          <Link className="primary-button" to="/monitors/new"><BellRing size={17} /> 新建通知规则</Link>
        </div>
      </header>

      <section className="notification-summary-grid" aria-label="通知概览">
        <NotifyMetric label="待发送" value={summary.pending} detail="等待通知 worker 发送" icon={<Clock3 size={18} />} tone="orange" />
        <NotifyMetric label="已发送" value={summary.sent} detail="成功触达的通知" icon={<CheckCircle2 size={18} />} tone="green" />
        <NotifyMetric label="失败" value={summary.failed} detail="需要重试或检查渠道" icon={<AlertTriangle size={18} />} tone="purple" />
        <NotifyMetric label="Webhook" value={summary.webhook} detail="自动化通知数量" icon={<Webhook size={18} />} tone="blue" />
      </section>

      <section className="notification-layout">
        <div className="panel notification-rules-panel">
          <div className="panel-heading">
            <div>
              <div className="panel-kicker">RULES</div>
              <h2>通知策略 / 通知规则</h2>
            </div>
            <span className="tag">真实规则 API</span>
          </div>
          <div className="rule-card-grid">
            {rules.map((rule, index) => {
              const summary = ruleSummary(rule);
              return (
              <article className="rule-card" key={rule.id}>
                <div className={`metric-icon ${index % 3 === 0 ? "blue" : index % 3 === 1 ? "orange" : "purple"}`}><BellRing size={17} /></div>
                <strong>{rule.name}</strong>
                <span>事件类型：{summary.types}</span>
                <span>严重程度：{summary.severity} 起推 · 处理状态：{summary.status}</span>
                <span>渠道：{summary.channel} · {rule.enabled ? "已启用" : "已停用"}</span>
                <span className="target-cell">{rule.site_name || "全部站点"} · {rule.target_url}</span>
              </article>
              );
            })}
          </div>
        </div>

        <aside className="panel channel-panel">
          <div className="panel-heading">
            <div>
              <div className="panel-kicker">CHANNELS</div>
              <h2>通知渠道</h2>
            </div>
          </div>
          <div className="channel-list-panel">
            {channelCards.map(({ label, icon: Icon, detail }) => (
              <div className="channel-row" key={label}>
                <Icon size={17} />
                <div>
                  <strong>{label}</strong>
                  <span>{detail}</span>
                </div>
              </div>
            ))}
          </div>
        </aside>
      </section>

      {message ? <div className={`operation-message ${message.type}`}>{message.text}</div> : null}

      <section className="panel notification-queue-panel">
        <div className="panel-heading">
          <div>
            <div className="panel-kicker">OUTBOX</div>
            <h2>通知队列</h2>
          </div>
          <select className="select-input compact-select" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} aria-label="通知状态筛选">
            <option value="all">全部状态</option>
            <option value="pending">待发送</option>
            <option value="sent">已发送</option>
            <option value="failed">失败</option>
          </select>
        </div>
        {filtered.length ? (
          <div className="notifications-table-wrap">
            <table className="notifications-table">
              <thead>
                <tr>
                  <th>事件</th>
                  <th>渠道</th>
                  <th>目标</th>
                  <th>状态</th>
                  <th>次数</th>
                  <th>时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <strong>{item.event_summary || item.product_title || "通知事件"}</strong>
                      <span className="table-sub">{item.site_name || "未知站点"} · {item.change_type || "未知类型"}</span>
                    </td>
                    <td>{item.channel || "webhook"}</td>
                    <td><span className="target-cell">{item.target_url || "未配置目标"}</span></td>
                    <td><span className={`notify-status ${item.status || "unknown"}`}>{statusLabel(item.status)}</span>{item.last_error ? <span className="table-sub error-text">{item.last_error}</span> : null}</td>
                    <td>{item.attempts ?? 0}</td>
                    <td><span className="time-cell"><Clock3 size={13} />{relativeTime(item.created_at || item.sent_at)}</span></td>
                    <td>
                      <button className="text-action" type="button" disabled={updatingId === item.id || item.status === "sent"} onClick={() => handleRetry(item.id)}>
                        {updatingId === item.id ? <RefreshCw size={14} className="spin" /> : <RotateCcw size={14} />} 重试通知
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            <div className="empty-icon"><Send size={20} /></div>
            <h3>当前没有通知记录</h3>
            <p>当监控规则产生新品、价格、库存或信息变化时，通知队列会显示发送状态。</p>
          </div>
        )}
      </section>
    </main>
  );
}

function NotifyMetric({ label, value, detail, icon, tone }: { label: string; value: string | number; detail: string; icon: React.ReactNode; tone: string }) {
  return (
    <div className="metric-card notification-summary-card">
      <div className={`metric-icon ${tone}`}>{icon}</div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}
