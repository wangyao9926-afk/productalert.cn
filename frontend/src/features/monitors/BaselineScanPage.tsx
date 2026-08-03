import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, ChevronLeft, CircleAlert, LoaderCircle, PackageSearch, RefreshCw, RotateCw } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { getScanJob, resumeScanJob, type ScanJob, triggerSiteScan } from "../../api/monitors";

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
        <button className="icon-button" type="button" onClick={() => jobId && void getScanJob(jobId).then(setJob)} aria-label="刷新扫描进度">
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
      ) : null}

      {baselineIncomplete ? (
        <div className="baseline-quality-warning" role="status">
          当前仅显示已验证入库的商品，官网目录仍不完整；请在限流冷却后继续扫描。
        </div>
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

function Metric({ label, value, detail, tone = "default" }: { label: string; value: number | string; detail: string; tone?: "default" | "warning" | "success" }) {
  return (
    <article className={`metric-card baseline-metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}
