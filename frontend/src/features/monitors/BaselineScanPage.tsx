import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, ChevronLeft, CircleAlert, ExternalLink, LoaderCircle, PackageSearch, RefreshCw, RotateCw } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { getScanJob, getScanJobCandidates, resumeScanJob, type ScanCandidate, type ScanCandidateEvidence, type ScanJob, triggerSiteScan } from "../../api/monitors";

const terminalStatuses = new Set(["success", "partial_success", "failed"]);

function displayStatus(status?: string) {
  if (status === "success") return "扫描完成";
  if (status === "partial_success") return "部分完成";
  if (status === "failed") return "扫描失败";
  if (status === "running") return "正在扫描";
  return "正在排队";
}

export function BaselineScanPage() {
  const navigate = useNavigate();
  const { siteId, jobId } = useParams();
  const [job, setJob] = useState<ScanJob | null>(null);
  const [candidateEvidence, setCandidateEvidence] = useState<ScanCandidateEvidence | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retrying, setRetrying] = useState(false);
  const [resuming, setResuming] = useState(false);

  useEffect(() => {
    if (!jobId) return undefined;
    let active = true;
    const refresh = async () => {
      try {
        const nextJob = await getScanJob(jobId);
        if (!active) return;
        setJob(nextJob);
        setError("");
        try {
          const nextEvidence = await getScanJobCandidates(jobId);
          if (active) setCandidateEvidence(nextEvidence);
        } catch {
          if (active) setCandidateEvidence(null);
        }
      } catch (requestError) {
        if (!active) return;
        if (requestError instanceof ApiError && requestError.status === 401) {
          setError("请先登录 ProductAlert API，才能查看扫描进度。");
        } else {
          setError("暂时无法读取扫描进度，请稍后重试。");
        }
      } finally {
        if (active) setLoading(false);
      }
    };

    void refresh();
    const timer = window.setInterval(() => {
      if (!job || !terminalStatuses.has(job.status)) void refresh();
    }, 2000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [job, jobId]);

  const progress = job?.result?.progress;
  const status = job?.status || "queued";
  const finished = terminalStatuses.has(status);
  const hasProducts = (progress?.product_count || 0) > 0;
  const canViewProducts = finished && status !== "failed" && hasProducts;
  const quality = progress?.quality;
  const baselineIncomplete = quality?.baseline_state === "incomplete";
  const catalogReferenceCount = quality?.catalog_reference_count;
  const coverageState = quality?.coverage_state;
  const discoverySources = Object.entries(quality?.discovery_source_counts || {});
  const adapterIssues = (quality?.adapter_attempts || []).filter((attempt) => ["limited", "blocked", "failed"].includes(attempt.status));
  const title = useMemo(() => displayStatus(status), [status]);

  const retry = async () => {
    if (!siteId) return;
    setRetrying(true);
    setError("");
    try {
      const nextJob = await triggerSiteScan(Number(siteId));
      navigate(`/monitors/${siteId}/baseline/${nextJob.id}`);
    } catch {
      setError("重新扫描未能创建，请检查后端服务和登录状态。");
      setRetrying(false);
    }
  };

  const resume = async () => {
    if (!jobId || !siteId) return;
    setResuming(true);
    setError("");
    try {
      const nextJob = await resumeScanJob(jobId);
      navigate(`/monitors/${siteId}/baseline/${nextJob.id}`);
    } catch {
      setError("无法创建继续扫描任务，请稍后重试。");
      setResuming(false);
    }
  };

  return (
    <main className="baseline-scan-page">
      <header className="page-header">
        <div>
          <Link className="back-link" to="/monitors"><ChevronLeft size={15} /> 返回监控中心</Link>
          <div className="eyebrow">FIRST BASELINE SCAN</div>
          <h1>首次扫描正在建立产品基线</h1>
          <p>首次结果只建立产品档案，不会把已有商品误报为新品；之后才会提醒真正的新品、价格和库存变化。</p>
        </div>
        <span className={`baseline-status ${status}`}>
          {status === "failed" ? <CircleAlert size={16} /> : status === "success" ? <CheckCircle2 size={16} /> : <LoaderCircle size={16} className="spin" />}
          {title}
        </span>
      </header>

      <section className="panel baseline-scan-hero" aria-live="polite">
        <div className="baseline-scan-icon"><PackageSearch size={24} /></div>
        <div>
          <div className="panel-kicker">SCAN PROGRESS</div>
          <h2>{loading ? "正在读取扫描任务…" : title}</h2>
          <p>{job?.message || "准备发现官网中的商品链接。"}</p>
        </div>
        <button
          className="icon-button"
          type="button"
          onClick={() => {
            if (!jobId) return;
            void Promise.all([getScanJob(jobId), getScanJobCandidates(jobId)])
              .then(([nextJob, nextEvidence]) => {
                setJob(nextJob);
                setCandidateEvidence(nextEvidence);
                setError("");
              })
              .catch(() => setError("暂时无法读取扫描进度，请稍后重试。"));
          }}
          aria-label="刷新扫描进度"
        >
          <RefreshCw size={16} />
        </button>
      </section>

      {error ? <div className="baseline-error" role="alert">{error}</div> : null}

      <section className="baseline-progress-grid" aria-label="首次扫描统计">
        <Metric label="已发现" value={progress?.discovered_count || 0} detail="商品候选链接" />
        <Metric label="已处理" value={progress?.processed_count || 0} detail="已完成字段提取" />
        <Metric label="失败" value={progress?.failed_count || 0} detail="需要复查的链接" tone="warning" />
        <Metric label="产品总数" value={progress?.product_count ?? "—"} detail={progress?.baseline_completed ? "基线已保存" : "等待扫描完成"} tone="success" />
      </section>

      {quality ? (
        <>
          <section className="baseline-quality-grid" aria-label="目录采集质量">
            <Metric label="已验证入库" value={quality.stored_product_count || 0} detail="已成功建立商品档案" tone="success" />
            <Metric label="待验证商品" value={quality.pending_retry_count || 0} detail="将在可访问时继续验证" tone="warning" />
            <Metric label="受限流" value={quality.rate_limited_count || 0} detail="官网暂时限制读取频率" tone="warning" />
            <Metric
              label="读取/解析失败"
              value={(quality.blocked_count || 0) + (quality.fetch_failed_count || 0) + (quality.parse_failed_count || 0)}
              detail="不会被当作已完成商品"
              tone="warning"
            />
          </section>
          <section className="baseline-catalog-coverage" aria-label="目录覆盖">
            <div>
              <div className="panel-kicker">CATALOG COVERAGE</div>
              <h2>目录覆盖</h2>
              <p>
                {typeof catalogReferenceCount === "number"
                  ? `已验证 ${quality.stored_product_count || 0} / 目录参考 ${catalogReferenceCount} 个商品`
                  : `已验证 ${quality.stored_product_count || 0} 个商品；未取得公开目录总数，不能将当前数量视为全站商品总数。`}
              </p>
            </div>
            <div className={`coverage-state ${coverageState || "pending"}`}>
              {coverageState === "verified" ? "已核验" : coverageState === "incomplete" ? "尚不完整" : coverageState === "best_effort" ? "尽力发现" : "正在计算"}
            </div>
            {discoverySources.length ? (
              <div className="coverage-sources" aria-label="发现来源">
                {discoverySources.map(([source, count]) => <span key={source}>{sourceLabel(source)} · {count}</span>)}
              </div>
            ) : null}
            {adapterIssues.length ? <small className="coverage-issues">{adapterIssues.map(adapterIssueLabel).join("；")}</small> : null}
          </section>
        </>
      ) : null}

      {baselineIncomplete ? (
        <div className="baseline-quality-warning" role="status">
          当前仅显示已验证入库的商品，官网目录仍不完整；请在限流冷却后继续扫描。
        </div>
      ) : null}

      {candidateEvidence ? (
        <section className="panel baseline-candidate-evidence" aria-label="扫描候选证据">
          <div className="baseline-candidate-heading">
            <div>
              <div className="panel-kicker">SCAN EVIDENCE</div>
              <h2>需要核对的候选链接</h2>
              <p>成功识别的商品已进入产品库；以下链接未计入产品数，可直接查看官网与失败原因。</p>
            </div>
            <span>已入库 {candidateEvidence.stored_count} · 待核对 {candidateEvidence.issue_count}</span>
          </div>
          {candidateEvidence.items.length ? (
            <div className="baseline-candidate-list">
              {candidateEvidence.items.map((candidate) => (
                <a className="baseline-candidate-row" key={candidate.id} href={candidate.url} target="_blank" rel="noreferrer">
                  <span className={`baseline-candidate-status ${candidate.status}`}>{candidateStatusLabel(candidate)}</span>
                  <span className="baseline-candidate-url">{candidate.url}</span>
                  <small>{candidateDetail(candidate)}</small>
                  <ExternalLink size={15} aria-hidden="true" />
                </a>
              ))}
            </div>
          ) : <div className="baseline-candidate-empty">本次扫描没有需要人工核对的候选链接。</div>}
          {candidateEvidence.truncated ? <small className="baseline-candidate-truncated">仅显示前 100 条待核对链接。</small> : null}
        </section>
      ) : null}

      <section className="panel baseline-next-step">
        <div>
          <div className="panel-kicker">NEXT STEP</div>
          <h2>{canViewProducts ? "产品基线已准备好" : "扫描结束后自动生成产品库"}</h2>
          <p>{canViewProducts ? "可以查看每个产品的价格、卖点、类型、库存与原始官网链接。" : "请保持此页面打开；系统会每 2 秒更新一次扫描结果。"}</p>
        </div>
        <div className="baseline-actions">
          {status === "failed" ? (
            <button className="primary-button" type="button" onClick={retry} disabled={retrying}>
              <RotateCw size={16} /> {retrying ? "正在重新创建任务…" : "重新扫描"}
            </button>
          ) : null}
          {canViewProducts ? <Link className="primary-button" to={`/products?site_id=${siteId}`}>查看产品库</Link> : null}
          {baselineIncomplete ? (
            <button className="secondary-button" type="button" onClick={resume} disabled={resuming}>
              <RotateCw size={16} /> {resuming ? "正在创建继续扫描…" : "继续扫描"}
            </button>
          ) : null}
        </div>
      </section>
    </main>
  );
}

function sourceLabel(source: string) {
  return ({ shopify_api: "Shopify 公开目录", woocommerce_store_api: "WooCommerce 公开目录", product_sitemap: "商品 Sitemap", sitemap: "Sitemap", html_links: "页面链接", json_ld_item_list: "JSON-LD", browser_render: "动态渲染" } as Record<string, string>)[source] || source;
}

function adapterIssueLabel(attempt: { adapter: string; status: string; http_status?: number; reason?: string }) {
  const adapter = sourceLabel(attempt.adapter);
  if (attempt.status === "limited") return `${adapter}：读取频率受限${attempt.http_status ? ` (${attempt.http_status})` : ""}`;
  if (attempt.status === "blocked") return `${adapter}：访问被拒绝${attempt.http_status ? ` (${attempt.http_status})` : ""}`;
  return `${adapter}：${attempt.reason || "读取失败"}${attempt.http_status ? ` (${attempt.http_status})` : ""}`;
}

function candidateStatusLabel(candidate: ScanCandidate) {
  return ({
    parse_failed: "未识别出商品信息",
    non_product: "非商品页",
    rate_limited: "官网限流",
    blocked: "访问受限",
    fetch_failed: "读取失败",
    http_error: "官网返回错误",
    timeout: "请求超时",
    unsupported_content: "页面内容不支持",
    pending_retry: "等待重试",
  } as Record<string, string>)[candidate.status] || candidate.error_category || "需要核对";
}

function candidateDetail(candidate: ScanCandidate) {
  const details = [candidate.http_status ? `HTTP ${candidate.http_status}` : null, candidate.error_category, candidate.attempt_count ? `已尝试 ${candidate.attempt_count} 次` : null];
  if (candidate.retry_after_seconds) details.push(`约 ${Math.ceil(candidate.retry_after_seconds / 60)} 分钟后重试`);
  return details.filter(Boolean).join(" · ") || "等待下一次扫描确认";
}

function Metric({ label, value, detail, tone = "default" }: { label: string; value: number | string; detail: string; tone?: "default" | "warning" | "success" }) {
  return (
    <article className={`metric-card baseline-metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}
