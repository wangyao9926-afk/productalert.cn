import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Archive,
  ArrowDown,
  ArrowUp,
  CheckCircle2,
  Clock3,
  Download,
  Eye,
  FileText,
  Filter,
  PackagePlus,
  RefreshCw,
  Search,
  Star,
  Tag,
  XCircle,
} from "lucide-react";
import { Link } from "react-router-dom";
import { loadChangeEvents, type ChangeEventFilters } from "../../api/changes";
import { ApiError } from "../../api/client";
import { updateChangeEventInboxStatus, type BackendInboxStatus } from "../../api/inbox";
import { loadOverview, type OverviewData } from "../../api/overview";
import type { ChangeEvent } from "../../types/api";

type InboxStatus = "unread" | "processed" | "false-positive" | "watched";
type Severity = "high" | "medium" | "low";

type InboxItem = {
  id: number;
  title: string;
  site: string;
  summary: string;
  type: string;
  typeLabel: string;
  severity: Severity;
  status: InboxStatus;
  createdAt: string;
  owner: string;
  note: string;
  followUp: boolean;
};

const changeTypeLabels: Record<string, string> = {
  new_product: "新品上新",
  price_changed: "价格变化",
  availability_changed: "库存变化",
  content_changed: "信息变化",
};

const changeTypeIcons: Record<string, typeof PackagePlus> = {
  new_product: PackagePlus,
  price_changed: Tag,
  availability_changed: Archive,
  content_changed: FileText,
};

const severityText: Record<Severity, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

const statusText: Record<InboxStatus, string> = {
  unread: "待处理",
  processed: "已处理",
  "false-positive": "误报",
  watched: "重点关注",
};

const ownerByStatus: Record<InboxStatus, string> = {
  unread: "运营值班",
  processed: "商品运营",
  "false-positive": "数据质检",
  watched: "竞品研究",
};

const noteByStatus: Record<InboxStatus, string> = {
  unread: "处理备注：待确认是否需要跟进采购、投放或竞品分析。",
  processed: "处理备注：已记录到运营任务，可进入复盘报告。",
  "false-positive": "误报原因：页面噪音或非商品核心字段变化。",
  watched: "处理备注：需跟进，建议持续观察 24 小时。",
};

function relativeTime(value?: string | null) {
  if (!value) return "刚刚";
  const minutes = Math.max(1, Math.round((Date.now() - new Date(value).getTime()) / 60000));
  if (minutes < 60) return `${minutes} 分钟前`;
  if (minutes < 1440) return `${Math.round(minutes / 60)} 小时前`;
  return `${Math.round(minutes / 1440)} 天前`;
}

function inferSeverity(event: ChangeEvent): Severity {
  if (event.change_type === "new_product" || event.change_type === "price_changed") return "high";
  if (event.change_type === "availability_changed") return "medium";
  return "low";
}

function normalizeInboxStatus(event: ChangeEvent): InboxStatus {
  const backendStatus = event.inbox_status || event.status;
  if (backendStatus === "read" || backendStatus === "reviewed" || backendStatus === "processed") return "processed";
  if (backendStatus === "false_positive" || backendStatus === "false-positive") return "false-positive";
  if (backendStatus === "important" || backendStatus === "watched") return "watched";
  return "unread";
}

function toInboxItems(data: OverviewData, localStatuses: Record<number, InboxStatus>): InboxItem[] {
  return data.events.map((event) => {
    const status = localStatuses[event.id] || normalizeInboxStatus(event);
    return {
      id: event.id,
      title: event.product_title || "未命名产品",
      site: event.site_name || "未知站点",
      summary: event.summary || "检测到页面信息变化",
      type: event.change_type || "content_changed",
      typeLabel: changeTypeLabels[event.change_type || ""] || "信息变化",
      severity: inferSeverity(event),
      status,
      createdAt: relativeTime(event.created_at),
      owner: event.assignee || ownerByStatus[status],
      note: event.review_note || event.false_positive_reason || noteByStatus[status],
      followUp: status === "watched",
    };
  });
}

function countBy(items: InboxItem[], predicate: (item: InboxItem) => boolean) {
  return items.filter(predicate).length;
}

export function InboxPage() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeType, setActiveType] = useState("all");
  const [activeSeverity, setActiveSeverity] = useState("all");
  const [activeStatus, setActiveStatus] = useState("all");
  const [activeSite, setActiveSite] = useState("all");
  const [activeAssignee, setActiveAssignee] = useState("all");
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [localStatuses, setLocalStatuses] = useState<Record<number, InboxStatus>>({});
  const [actionMessage, setActionMessage] = useState("");
  const [actionTone, setActionTone] = useState<"success" | "error" | "idle">("idle");
  const [updatingId, setUpdatingId] = useState<number | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [query]);

  const backendStatusFilter = (status: string) => {
    if (status === "processed") return "read";
    if (status === "watched") return "important";
    if (status === "false-positive") return "false_positive";
    if (status === "unread") return "unread";
    return undefined;
  };

  const changeEventFilters = useMemo<ChangeEventFilters>(() => ({
    site_id: activeSite,
    change_type: activeType,
    inbox_status: backendStatusFilter(activeStatus),
    assignee: activeAssignee,
    severity: activeSeverity,
    q: debouncedQuery,
  }), [activeAssignee, activeSeverity, activeSite, activeStatus, activeType, debouncedQuery]);

  const refresh = useCallback(() => {
    setLoading(true);
    loadOverview()
      .then(async (overview) => {
        const events = overview.live
          ? await loadChangeEvents(changeEventFilters).catch(() => overview.events)
          : overview.events;
        setData({ ...overview, events });
      })
      .finally(() => setLoading(false));
  }, [changeEventFilters]);

  useEffect(refresh, [refresh]);

  const items = useMemo(() => (data ? toInboxItems(data, localStatuses) : []), [data, localStatuses]);

  const filteredItems = useMemo(() => {
    return items.filter((item) => {
      const queryMatch = !query.trim() || `${item.title} ${item.site} ${item.summary}`.toLowerCase().includes(query.trim().toLowerCase());
      return queryMatch;
    });
  }, [items, query]);

  const actionErrorMessage = (error: unknown) => {
    if (error instanceof ApiError && error.status === 401) return "请先登录 ProductAlert API，再处理情报。";
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

  const backendStatusFor = (status: InboxStatus): BackendInboxStatus => {
    if (status === "processed") return "read";
    if (status === "watched") return "important";
    if (status === "false-positive") return "false_positive";
    return "unread";
  };

  const reviewPayloadFor = (status: InboxStatus) => ({
    inbox_status: backendStatusFor(status),
    assignee: ownerByStatus[status],
    review_note: noteByStatus[status],
    false_positive_reason: status === "false-positive" ? "非核心字段变化" : null,
  });

  const setStatus = async (id: number, status: InboxStatus) => {
    setUpdatingId(id);
    setActionMessage("");
    setActionTone("idle");
    try {
      await updateChangeEventInboxStatus(id, reviewPayloadFor(status));
      setLocalStatuses((current) => ({ ...current, [id]: status }));
      setActionTone("success");
      setActionMessage(`操作成功：已${statusText[status]}。`);
      refresh();
    } catch (error) {
      setActionTone("error");
      setActionMessage(actionErrorMessage(error));
    } finally {
      setUpdatingId(null);
    }
  };

  const batchProcess = async () => {
    setActionMessage("");
    setActionTone("idle");
    try {
      await Promise.all(filteredItems.map((item) => updateChangeEventInboxStatus(item.id, reviewPayloadFor("processed"))));
      setLocalStatuses((current) => {
        const next = { ...current };
        filteredItems.forEach((item) => { next[item.id] = "processed"; });
        return next;
      });
      setActionTone("success");
      setActionMessage(`操作成功：已批量处理 ${filteredItems.length} 条情报。`);
      refresh();
    } catch (error) {
      setActionTone("error");
      setActionMessage(actionErrorMessage(error));
    }
  };

  if (loading || !data) {
    return <div className="page-loading"><RefreshCw size={18} className="spin" /> 正在同步情报收件箱…</div>;
  }

  return (
    <main className="inbox-page">
      <header className="page-header">
        <div>
          <div className="eyebrow">INTELLIGENCE INBOX</div>
          <h1>情报收件箱</h1>
          <p>把新品上新、价格变化、库存变化和信息变化聚合成可处理的运营任务。</p>
          <p className="workflow-hint">运营处理流：处理状态、负责人、处理备注、需跟进和误报原因会沉淀到每条变化记录。</p>
        </div>
        <div className="page-actions">
          <button className="icon-button" type="button" onClick={refresh} aria-label="刷新情报收件箱"><RefreshCw size={17} /></button>
          <button className="button button-secondary" type="button"><Download size={16} /> 导出 CSV</button>
          <button className="primary-button" type="button" onClick={batchProcess}><CheckCircle2 size={17} /> 批量处理</button>
        </div>
      </header>

      <section className="inbox-summary-grid" aria-label="情报概览">
        <InboxSummary label="待处理" value={countBy(items, (item) => item.status === "unread")} icon={<AlertTriangle size={18} />} tone="orange" />
        <InboxSummary label="重点关注" value={countBy(items, (item) => item.status === "watched")} icon={<Star size={18} />} tone="purple" />
        <InboxSummary label="高严重程度" value={countBy(items, (item) => item.severity === "high")} icon={<ArrowUp size={18} />} tone="blue" />
        <InboxSummary label="已处理" value={countBy(items, (item) => item.status === "processed")} icon={<CheckCircle2 size={18} />} tone="green" />
      </section>

      <section className="panel inbox-controls" aria-label="情报筛选">
        <div className="monitor-search">
          <Search size={15} aria-hidden="true" />
          <input value={query} onChange={(event) => setQuery(event.target.value)} type="search" placeholder="搜索产品、品牌或变化摘要" aria-label="搜索产品、品牌或变化摘要" />
        </div>
        <select className="select-input compact-select" value={activeSite} onChange={(event) => setActiveSite(event.target.value)} aria-label="站点筛选">
          <option value="all">全部站点</option>
          {data.sites.map((site) => (
            <option value={site.id} key={site.id}>{site.name}</option>
          ))}
        </select>
        <select className="select-input compact-select" value={activeType} onChange={(event) => setActiveType(event.target.value)} aria-label="变化类型">
          <option value="all">全部类型</option>
          <option value="new_product">新品上新</option>
          <option value="price_changed">价格变化</option>
          <option value="availability_changed">库存变化</option>
          <option value="content_changed">信息变化</option>
        </select>
        <select className="select-input compact-select" value={activeSeverity} onChange={(event) => setActiveSeverity(event.target.value)} aria-label="严重程度">
          <option value="all">全部严重程度</option>
          <option value="high">严重程度 高</option>
          <option value="medium">严重程度 中</option>
          <option value="low">严重程度 低</option>
        </select>
        <select className="select-input compact-select" value={activeStatus} onChange={(event) => setActiveStatus(event.target.value)} aria-label="处理状态">
          <option value="all">全部处理状态</option>
          <option value="unread">待处理</option>
          <option value="processed">已处理</option>
          <option value="false-positive">误报</option>
          <option value="watched">需跟进</option>
        </select>
        <select className="select-input compact-select" value={activeAssignee} onChange={(event) => setActiveAssignee(event.target.value)} aria-label="负责人筛选">
          <option value="all">全部负责人</option>
          <option value="运营值班">运营值班</option>
          <option value="商品运营">商品运营</option>
          <option value="数据质检">数据质检</option>
          <option value="竞品研究">竞品研究</option>
        </select>
        <button className="button button-secondary" type="button"><Filter size={15} /> 筛选</button>
      </section>

      {actionMessage ? <div className={`operation-message ${actionTone}`} role="status">{actionMessage}</div> : null}

      <section className="panel inbox-list-panel">
        <div className="panel-heading">
          <div>
            <div className="panel-kicker">REVIEW QUEUE</div>
            <h2>待审阅变化</h2>
          </div>
          <span className="monitor-count">{filteredItems.length} 条情报</span>
        </div>
        <div className="inbox-list">
          {filteredItems.length ? filteredItems.map((item) => <InboxRow key={item.id} item={item} updating={updatingId === item.id} onStatus={setStatus} />) : <InboxEmpty />}
        </div>
      </section>
    </main>
  );
}

function InboxSummary({ label, value, icon, tone }: { label: string; value: string | number; icon: React.ReactNode; tone: string }) {
  return (
    <div className="metric-card inbox-summary-card">
      <div className={`metric-icon ${tone}`}>{icon}</div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>当前筛选范围</small>
      </div>
    </div>
  );
}

function InboxRow({ item, updating, onStatus }: { item: InboxItem; updating: boolean; onStatus: (id: number, status: InboxStatus) => void }) {
  const Icon = changeTypeIcons[item.type] || FileText;

  return (
    <article className={`inbox-row ${item.status}`}>
      <div className={`inbox-type-icon ${item.type}`}>
        <Icon size={17} />
      </div>
      <div className="inbox-row-main">
        <div className="inbox-row-title">
          <strong>{item.title}</strong>
          <span className="tag">{item.typeLabel}</span>
          <span className={`severity-badge ${item.severity}`}>严重程度 {severityText[item.severity]}</span>
          <span className={`status-badge ${item.status}`}>{statusText[item.status]}</span>
        </div>
        <p>{item.summary}</p>
        <div className="inbox-row-meta">
          <span>{item.site}</span>
          <span><Clock3 size={13} />{item.createdAt}</span>
          <span>负责人：{item.owner}</span>
          {item.followUp ? <span className="follow-up-flag">需跟进</span> : null}
        </div>
        <div className="inbox-workflow-note">{item.note}</div>
      </div>
      <div className="inbox-row-actions">
        <button className="text-action" type="button" disabled={updating} onClick={() => onStatus(item.id, "processed")}><CheckCircle2 size={14} /> 标记已处理</button>
        <button className="text-action" type="button" disabled={updating} onClick={() => onStatus(item.id, "false-positive")}><XCircle size={14} /> 标记误报</button>
        <button className="text-action" type="button" disabled={updating} onClick={() => onStatus(item.id, "watched")}><Star size={14} /> 重点关注</button>
        <Link className="icon-action" to={`/changes/${item.id}`} aria-label={`${item.title} 查看详情`} title="查看详情"><Eye size={14} /></Link>
      </div>
    </article>
  );
}

function InboxEmpty() {
  return (
    <div className="empty-state">
      <div className="empty-icon"><ArrowDown size={20} /></div>
      <h3>当前筛选下没有情报</h3>
      <p>调整变化类型、严重程度或搜索条件后再查看。</p>
    </div>
  );
}
