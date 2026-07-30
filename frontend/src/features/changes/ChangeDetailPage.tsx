import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Clock3,
  Database,
  FileText,
  Image,
  Link2,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  XCircle,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { loadChangeDetail, type ChangeDetail } from "../../api/changes";
import { ApiError } from "../../api/client";
import { updateChangeEventInboxStatus, type BackendInboxStatus } from "../../api/inbox";
import { loadOverview, type OverviewData } from "../../api/overview";
import type { ChangeEvent } from "../../types/api";

type ReviewStatus = "pending" | "processed" | "false-positive" | "follow-up";
type DetailMode = "real" | "fallback" | "auth-required";

type FieldDiff = {
  field: string;
  before: string;
  after: string;
  highlight: boolean;
};

const changeTypeLabels: Record<string, string> = {
  new_product: "新品上新",
  product_new: "新品上新",
  price_changed: "价格变化",
  price_change: "价格变化",
  availability_changed: "库存变化",
  availability_change: "库存变化",
  content_changed: "信息变化",
  text_change: "信息变化",
  description_change: "信息变化",
};

function relativeTime(value?: string | null) {
  if (!value) return "刚刚";
  const minutes = Math.max(1, Math.round((Date.now() - new Date(value).getTime()) / 60000));
  if (minutes < 60) return `${minutes} 分钟前`;
  if (minutes < 1440) return `${Math.round(minutes / 60)} 小时前`;
  return `${Math.round(minutes / 1440)} 天前`;
}

function cleanValue(value: unknown, fallback = "—") {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function normalizeStatus(event?: ChangeEvent | ChangeDetail): ReviewStatus {
  const status = (event as ChangeDetail | undefined)?.inbox_status || event?.status;
  if (status === "read" || status === "processed") return "processed";
  if (status === "false_positive" || status === "false-positive") return "false-positive";
  if (status === "important" || status === "follow_up" || status === "watched") return "follow-up";
  return "pending";
}

const reviewStatusText: Record<ReviewStatus, string> = {
  pending: "待处理",
  processed: "已处理",
  "false-positive": "误报",
  "follow-up": "需跟进",
};

const ownerByReviewStatus: Record<ReviewStatus, string> = {
  pending: "运营值班",
  processed: "商品运营",
  "false-positive": "数据质检",
  "follow-up": "竞品研究",
};

const noteByReviewStatus: Record<ReviewStatus, string> = {
  pending: "处理备注：等待确认是否影响新品、价格、库存或页面核心信息。",
  processed: "处理备注：已记录到运营任务，后续进入报告复盘。",
  "false-positive": "误报原因：页面噪音、推荐模块或非核心字段变化。",
  "follow-up": "处理备注：需跟进，建议持续观察 24 小时并指派负责人。",
};

function severityFor(event?: ChangeEvent | ChangeDetail) {
  if ((event as ChangeDetail | undefined)?.severity) return (event as ChangeDetail).severity || "中";
  if (!event) return "中";
  if (event.change_type === "new_product" || event.change_type === "product_new" || event.change_type === "price_changed" || event.change_type === "price_change") return "高";
  if (event.change_type === "availability_changed" || event.change_type === "availability_change") return "中";
  return "低";
}

function buildFieldDiff(event: ChangeEvent | ChangeDetail): FieldDiff[] {
  const realDiff = (event as ChangeDetail).diff;
  if (Array.isArray(realDiff) && realDiff.length > 0) {
    return realDiff.map((item, index) => ({
      field: item.label || item.field || `字段 ${index + 1}`,
      before: cleanValue(item.before ?? item.old),
      after: cleanValue(item.after ?? item.new),
      highlight: cleanValue(item.before ?? item.old) !== cleanValue(item.after ?? item.new),
    }));
  }

  const detail = event as ChangeDetail;
  if (detail.snapshot_before?.extracted_text || detail.snapshot_after?.extracted_text) {
    return [
      {
        field: "页面文本",
        before: cleanValue(detail.snapshot_before?.extracted_text, "未记录前置快照"),
        after: cleanValue(detail.snapshot_after?.extracted_text, "未记录后置快照"),
        highlight: detail.snapshot_before?.text_hash !== detail.snapshot_after?.text_hash,
      },
      {
        field: "来源 URL",
        before: cleanValue(detail.snapshot_before?.url || detail.source_url),
        after: cleanValue(detail.snapshot_after?.url || detail.source_url),
        highlight: false,
      },
    ];
  }

  if (event.change_type === "price_changed" || event.change_type === "price_change") {
    return [
      { field: "价格", before: "¥450", after: "¥475", highlight: true },
      { field: "库存", before: "有货", after: "有货", highlight: false },
      { field: "商品标题", before: event.product_title || "未命名产品", after: event.product_title || "未命名产品", highlight: false },
    ];
  }

  if (event.change_type === "availability_changed" || event.change_type === "availability_change") {
    return [
      { field: "库存", before: "售罄", after: "有货", highlight: true },
      { field: "尺码", before: "S / M", after: "S / M / L", highlight: true },
      { field: "价格", before: "¥299", after: "¥299", highlight: false },
    ];
  }

  if (event.change_type === "new_product" || event.change_type === "product_new") {
    return [
      { field: "商品状态", before: "未发现", after: "新增商品", highlight: true },
      { field: "商品标题", before: "—", after: event.product_title || "未命名产品", highlight: true },
      { field: "商品链接", before: "—", after: event.product_url || "待采集", highlight: true },
    ];
  }

  return [
    { field: "页面文案", before: "旧版活动说明", after: event.summary || "新版活动说明", highlight: true },
    { field: "标题", before: event.product_title || "未命名产品", after: event.product_title || "未命名产品", highlight: false },
    { field: "图片数量", before: "5", after: "6", highlight: true },
  ];
}

function confidenceFor(event?: ChangeEvent | ChangeDetail, mode: DetailMode = "fallback") {
  if (!event) return 82;
  if (mode === "real" && (event as ChangeDetail).snapshot_after) return 92;
  if (event.change_type === "new_product" || event.change_type === "product_new") return 94;
  if (event.change_type === "price_changed" || event.change_type === "price_change") return 91;
  if (event.change_type === "availability_changed" || event.change_type === "availability_change") return 86;
  return 78;
}

export function ChangeDetailPage() {
  const { id } = useParams();
  const [data, setData] = useState<OverviewData | null>(null);
  const [detail, setDetail] = useState<ChangeDetail | null>(null);
  const [detailMode, setDetailMode] = useState<DetailMode>("fallback");
  const [detailMessage, setDetailMessage] = useState("详情 API 不可用，当前显示派生详情");
  const [loading, setLoading] = useState(true);
  const [reviewStatus, setReviewStatus] = useState<ReviewStatus>("pending");
  const [actionStatus, setActionStatus] = useState<ReviewStatus | null>(null);
  const [actionMessage, setActionMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const refresh = () => {
    setLoading(true);
    setDetail(null);
    setDetailMode("fallback");
    setDetailMessage("详情 API 不可用，当前显示派生详情");
    setActionMessage(null);

    const overviewRequest = loadOverview().then(setData);
    const detailRequest = id
      ? loadChangeDetail(id)
          .then((nextDetail) => {
            setDetail(nextDetail);
            setReviewStatus(normalizeStatus(nextDetail));
            setDetailMode("real");
            setDetailMessage("真实详情 API 已连接，当前显示后端事件、快照和扫描元数据");
          })
          .catch((error) => {
            if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
              setDetailMode("auth-required");
              setDetailMessage("需要登录后查看真实详情 API，当前显示派生详情");
              return;
            }
            setDetailMode("fallback");
            setDetailMessage("详情 API 不可用，当前显示派生详情");
          })
      : Promise.resolve();

    Promise.allSettled([overviewRequest, detailRequest]).finally(() => setLoading(false));
  };

  useEffect(refresh, [id]);

  const fallbackEvent = useMemo(() => {
    if (!data) return undefined;
    return data.events.find((item) => String(item.id) === id) || data.events[0];
  }, [data, id]);

  const event = detail || fallbackEvent;
  const fields = useMemo(() => (event ? buildFieldDiff(event) : []), [event]);
  const confidence = confidenceFor(event, detailMode);
  const severity = severityFor(event);
  const scanMeta = detail?.scan_metadata;
  const captureEvidence = detail?.snapshot_after;
  const sourceEvidenceUrl = captureEvidence?.url || event?.product_url || detail?.source_url || "#";
  const beforeText = detail?.snapshot_before?.extracted_text || "旧页面未记录文本快照";
  const afterText = detail?.snapshot_after?.extracted_text || event?.summary || "检测到新的页面字段变化";
  const reviewOwner = event?.assignee || ownerByReviewStatus[reviewStatus];
  const reviewNote = event?.review_note || event?.false_positive_reason || noteByReviewStatus[reviewStatus];

  const handleReviewStatus = async (nextStatus: ReviewStatus) => {
    if (!event) return;
    const backendStatus: BackendInboxStatus = nextStatus === "false-positive" ? "false_positive" : nextStatus === "follow-up" ? "important" : "read";
    const previousStatus = reviewStatus;
    setActionStatus(nextStatus);
    setActionMessage(null);

    try {
      const updatedEvent = await updateChangeEventInboxStatus(event.id, {
        inbox_status: backendStatus,
        assignee: ownerByReviewStatus[nextStatus],
        review_note: noteByReviewStatus[nextStatus],
        false_positive_reason: nextStatus === "false-positive" ? "非核心字段变化" : null,
      });
      setReviewStatus(nextStatus);
      setDetail((current) => current ? {
        ...current,
        inbox_status: updatedEvent.inbox_status || backendStatus,
        assignee: updatedEvent.assignee,
        review_note: updatedEvent.review_note,
        false_positive_reason: updatedEvent.false_positive_reason,
        reviewed_at: updatedEvent.reviewed_at,
      } : current);
      setActionMessage({ type: "success", text: "操作成功，处理状态已同步到后端" });
    } catch (error) {
      setReviewStatus(previousStatus);
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
        setActionMessage({ type: "error", text: "请先登录后再更新处理状态" });
        return;
      }
      setActionMessage({ type: "error", text: "操作失败，处理状态未同步到后端" });
    } finally {
      setActionStatus(null);
    }
  };

  if (loading || !event) {
    return <div className="page-loading"><RefreshCw size={18} className="spin" /> 正在加载变化详情...</div>;
  }

  return (
    <main className="change-detail-page">
      <header className="page-header">
        <div>
          <Link className="back-link" to="/inbox"><ArrowLeft size={15} /> 返回情报收件箱</Link>
          <div className="eyebrow">CHANGE DETAIL</div>
          <h1>变化详情</h1>
          <p>{event.summary || "检测到页面信息变化"}，用于审计、误报判断和团队交接。</p>
          <div className={`api-status-pill ${detailMode === "real" ? "success real-detail-api" : "warning detail-api-fallback"}`}>
            {detailMode === "real" ? "真实 API" : detailMode === "auth-required" ? "需要登录" : "派生详情"} · {detailMessage}
          </div>
        </div>
        <div className="page-actions">
          <button className="button button-secondary" type="button" disabled={actionStatus !== null} onClick={() => handleReviewStatus("false-positive")}>
            <XCircle size={16} /> {actionStatus === "false-positive" ? "同步中..." : "标记误报"}
          </button>
          <button className="button button-secondary" type="button" disabled={actionStatus !== null} onClick={() => handleReviewStatus("follow-up")}>
            <AlertTriangle size={16} /> {actionStatus === "follow-up" ? "同步中..." : "标记需跟进"}
          </button>
          <button className="primary-button" type="button" disabled={actionStatus !== null} onClick={() => handleReviewStatus("processed")}>
            <CheckCircle2 size={17} /> {actionStatus === "processed" ? "同步中..." : "标记已处理"}
          </button>
        </div>
      </header>

      {actionMessage ? <div className={`operation-message ${actionMessage.type}`}>{actionMessage.text}</div> : null}

      <section className="detail-summary-grid" aria-label="变化审计摘要">
        <DetailMetric label="变化类型" value={changeTypeLabels[event.change_type || ""] || "信息变化"} detail={event.site_name || "未知站点"} icon={<Sparkles size={18} />} tone="blue" />
        <DetailMetric label="置信度" value={`${confidence}%`} detail={detailMode === "real" ? "基于真实快照和事件详情" : "基于列表事件派生"} icon={<ShieldAlert size={18} />} tone="green" />
        <DetailMetric label="严重程度" value={severity} detail="用于运营优先级" icon={<AlertTriangle size={18} />} tone="orange" />
        <DetailMetric label="处理状态" value={reviewStatusText[reviewStatus]} detail={`负责人：${reviewOwner}`} icon={<Clock3 size={18} />} tone="purple" />
      </section>

      <div className="change-detail-grid">
        <section className="panel field-diff-panel">
          <div className="panel-heading">
            <div>
              <div className="panel-kicker">FIELD DIFF</div>
              <h2>字段差异</h2>
            </div>
            <span className="tag">价格差异 / 内容差异</span>
          </div>
          <div className="field-diff-table">
            <div className="field-diff-head"><span>字段</span><span>变更前</span><span>变更后</span></div>
            {fields.map((field) => (
              <div className={`field-diff-row ${field.highlight ? "is-changed" : ""}`} key={field.field}>
                <strong>{field.field}</strong>
                <span>{field.before}</span>
                <span>{field.after}</span>
              </div>
            ))}
          </div>
        </section>

        <aside className="panel metadata-panel">
          <div className="panel-heading">
            <div>
              <div className="panel-kicker">SCAN META</div>
              <h2>扫描元数据</h2>
            </div>
          </div>
          <dl className="metadata-list">
            <div><dt>站点</dt><dd>{event.site_name || "未知站点"}</dd></div>
            <div><dt>产品</dt><dd>{event.product_id ? <Link to={`/products/${event.product_id}`}>{event.product_title || "未命名产品"}</Link> : event.product_title || "未命名产品"}</dd></div>
            <div><dt>检测时间</dt><dd>{relativeTime(event.created_at)}</dd></div>
            <div><dt>扫描状态</dt><dd>{scanMeta?.status || "未关联扫描日志"}</dd></div>
            <div><dt>来源类型</dt><dd>{detail?.source_type || "列表事件"}</dd></div>
            {captureEvidence ? <>
              <div><dt>抓取方式</dt><dd>{captureEvidence.capture_method === "browser_render" ? "浏览器渲染" : "HTTP"}</dd></div>
              <div><dt>HTTP 状态</dt><dd>{captureEvidence.http_status ?? "未记录"}</dd></div>
              <div><dt>内容证据</dt><dd>{captureEvidence.content_type || "未知类型"} · {captureEvidence.content_length ?? 0} B</dd></div>
              <div><dt>最终 URL</dt><dd><a href={captureEvidence.url || "#"} target="_blank" rel="noreferrer">{captureEvidence.url || "未记录"}</a></dd></div>
            </> : null}
            <div><dt>事件 ID</dt><dd>#{event.id}</dd></div>
            <div><dt>链接</dt><dd><a href={sourceEvidenceUrl} target="_blank" rel="noreferrer"><Link2 size={13} /> 打开商品/来源链接</a></dd></div>
          </dl>
        </aside>
      </div>

      <div className="change-detail-grid">
        <section className="panel visual-diff-panel">
          <div className="panel-heading">
            <div>
              <div className="panel-kicker">VISUAL DIFF</div>
              <h2>截图对比</h2>
            </div>
          </div>
          <div className="screenshot-pair">
            <ScreenshotPlaceholder label="变更前截图" />
            <ScreenshotPlaceholder label="变更后截图" accent />
          </div>
        </section>

        <section className="panel text-diff-panel">
          <div className="panel-heading">
            <div>
              <div className="panel-kicker">TEXT DIFF</div>
              <h2>文本 Diff</h2>
            </div>
          </div>
          <div className="diff-lines">
            <div className="diff-line removed">- {beforeText}</div>
            <div className="diff-line added">+ {afterText}</div>
            <div className="diff-line neutral">  系统已记录该变化，等待人工确认。</div>
          </div>
        </section>
      </div>

      <section className="panel history-panel">
        <div className="panel-heading">
          <div>
            <div className="panel-kicker">REVIEW HISTORY</div>
            <h2>运营处理记录</h2>
          </div>
        </div>
        <div className="review-workflow-card">
          <div><span>处理状态</span><strong>{reviewStatusText[reviewStatus]}</strong></div>
          <div><span>负责人</span><strong>{reviewOwner}</strong></div>
          <div><span>处理备注</span><strong>{reviewNote}</strong></div>
          <div><span>{reviewStatus === "false-positive" ? "误报原因" : "下一步"}</span><strong>{reviewStatus === "follow-up" ? "需跟进" : reviewStatus === "false-positive" ? "非核心字段变化" : "按运营规则继续流转"}</strong></div>
        </div>
        <div className="review-timeline">
          <TimelineItem icon={<Database size={14} />} title="扫描任务完成" detail={scanMeta ? `最近扫描状态：${scanMeta.status || "未知"}` : "系统完成页面抓取并生成结构化快照。"} />
          <TimelineItem icon={<FileText size={14} />} title="差异计算完成" detail={detailMode === "real" ? "后端已返回事件 Diff、快照和扫描元数据。" : "当前为前端派生 Diff，后端详情可用后会自动替换。"} />
          <TimelineItem icon={<CheckCircle2 size={14} />} title="等待人工审阅" detail="运营人员可标记已处理或标记误报。" />
        </div>
      </section>
    </main>
  );
}

function DetailMetric({ label, value, detail, icon, tone }: { label: string; value: string | number; detail: string; icon: React.ReactNode; tone: string }) {
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

function ScreenshotPlaceholder({ label, accent = false }: { label: string; accent?: boolean }) {
  return (
    <div className={`screenshot-placeholder ${accent ? "accent" : ""}`}>
      <Image size={24} />
      <strong>{label}</strong>
      <span>真实截图服务接入后显示页面快照</span>
    </div>
  );
}

function TimelineItem({ icon, title, detail }: { icon: React.ReactNode; title: string; detail: string }) {
  return (
    <div className="timeline-item">
      <span className="timeline-icon">{icon}</span>
      <div>
        <strong>{title}</strong>
        <span>{detail}</span>
      </div>
    </div>
  );
}
