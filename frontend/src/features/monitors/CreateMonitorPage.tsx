import { useMemo, useState } from "react";
import {
  BellRing,
  CheckCircle2,
  ChevronLeft,
  Code2,
  Eye,
  FileText,
  Image,
  Link2,
  PackagePlus,
  Radio,
  Save,
  SearchCheck,
  ShieldCheck,
  Sparkles,
  Tags,
} from "lucide-react";
import { Link } from "react-router-dom";
import { ApiError } from "../../api/client";
import { createMonitorTask } from "../../api/monitors";

type MonitorTarget = {
  id: string;
  label: string;
  description: string;
  icon: typeof Sparkles;
};

const targets: MonitorTarget[] = [
  { id: "new-products", label: "新品上新", description: "识别集合页新增商品、首发 SKU 和新品入口", icon: PackagePlus },
  { id: "price", label: "价格变化", description: "跟踪售价、折扣价、划线价和币种变化", icon: Tags },
  { id: "stock", label: "库存变化", description: "监控售罄、补货、尺码和颜色可售状态", icon: ShieldCheck },
  { id: "text", label: "文本变化", description: "检测标题、描述、公告和活动文案变化", icon: FileText },
  { id: "image", label: "图片变化", description: "关注主图、详情图和视觉素材更新", icon: Image },
  { id: "area", label: "选区变化", description: "后续可绑定页面指定区域或截图选区", icon: Eye },
];

const extractionMethods = [
  { id: "auto", label: "自动识别", description: "适合大多数商品列表和标准详情页", icon: SearchCheck },
  { id: "css", label: "CSS 选择器", description: "为价格、标题、库存字段指定选择器", icon: Code2 },
  { id: "advanced", label: "高级规则", description: "预留给动态页面、登录页和复杂规则", icon: Radio },
];

const frequencies = ["每 15 分钟", "每 30 分钟", "每 60 分钟", "每天 09:00"];

const notificationChannels = ["站内情报收件箱", "邮件通知", "飞书/企微预留"];

export function CreateMonitorPage() {
  const [targetUrl, setTargetUrl] = useState("https://example.com/collections/new-arrivals");
  const [selectedTargets, setSelectedTargets] = useState<string[]>(["new-products", "price", "stock"]);
  const [extractionMethod, setExtractionMethod] = useState("auto");
  const [frequency, setFrequency] = useState("每 60 分钟");
  const [channels, setChannels] = useState<string[]>(["站内情报收件箱"]);
  const [saved, setSaved] = useState(false);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "success" | "error">("idle");
  const [saveMessage, setSaveMessage] = useState("");

  const selectedTargetLabels = useMemo(
    () => targets.filter((target) => selectedTargets.includes(target.id)).map((target) => target.label),
    [selectedTargets],
  );

  const selectedMethod = extractionMethods.find((method) => method.id === extractionMethod) || extractionMethods[0];

  const toggleTarget = (id: string) => {
    setSaved(false);
    setSaveState("idle");
    setSelectedTargets((current) => {
      if (current.includes(id)) return current.length === 1 ? current : current.filter((item) => item !== id);
      return [...current, id];
    });
  };

  const toggleChannel = (channel: string) => {
    setSaved(false);
    setSaveState("idle");
    setChannels((current) => {
      if (current.includes(channel)) return current.length === 1 ? current : current.filter((item) => item !== channel);
      return [...current, channel];
    });
  };

  const resetSaveState = () => {
    setSaved(false);
    setSaveState("idle");
    setSaveMessage("");
  };

  const saveMonitor = async () => {
    setSaved(false);
    setSaveState("saving");
    setSaveMessage("");
    try {
      const result = await createMonitorTask({
        targetUrl,
        targets: selectedTargets,
        extractionMethod,
        frequency,
        channels,
      });
      setSaved(true);
      setSaveState("success");
      setSaveMessage(`保存到真实后端成功：站点 #${result.site.id}，监控源 #${result.source.id}。`);
    } catch (error) {
      setSaveState("error");
      if (error instanceof ApiError && error.status === 401) {
        setSaveMessage("请先登录 ProductAlert API，然后再保存监控任务。");
        return;
      }
      if (error instanceof ApiError) {
        try {
          const parsed = JSON.parse(error.body) as { detail?: string };
          setSaveMessage(parsed.detail || `保存失败：API 返回 ${error.status}`);
        } catch {
          setSaveMessage(error.body || `保存失败：API 返回 ${error.status}`);
        }
        return;
      }
      setSaveMessage("保存失败：API 不可用，请确认后端服务已启动。");
    }
  };

  return (
    <main className="create-monitor-page">
      <header className="page-header">
        <div>
          <Link className="back-link" to="/monitors"><ChevronLeft size={15} /> 返回监控中心</Link>
          <div className="eyebrow">CREATE MONITOR</div>
          <h1>新建监控</h1>
          <p>为品牌官网、集合页或商品页创建一个可持续检测的监控任务。</p>
        </div>
        <div className="page-actions">
          <button className="primary-button" type="button" onClick={saveMonitor} disabled={saveState === "saving"}>
            <Save size={17} /> {saveState === "saving" ? "正在保存…" : "保存监控"}
          </button>
        </div>
      </header>

      <div className="wizard-layout">
        <aside className="panel wizard-steps" aria-label="新建监控步骤">
          {["目标 URL", "监控目标", "抓取方式", "监控频率"].map((step, index) => (
            <div className="wizard-step is-active" key={step}>
              <span>{index + 1}</span>
              <strong>{step}</strong>
            </div>
          ))}
        </aside>

        <section className="wizard-main">
          <section className="panel wizard-section">
            <div className="wizard-section-heading">
              <div className="section-icon"><Link2 size={17} /></div>
              <div>
                <div className="panel-kicker">STEP 1</div>
                <h2>目标 URL</h2>
              </div>
            </div>
            <label className="field-label" htmlFor="target-url">官网、集合页或商品页地址</label>
            <input
              id="target-url"
              className="url-input"
              value={targetUrl}
              onChange={(event) => { setTargetUrl(event.target.value); resetSaveState(); }}
              placeholder="https://brand.com/collections/new"
              type="url"
            />
          </section>

          <section className="panel wizard-section">
            <div className="wizard-section-heading">
              <div className="section-icon"><Sparkles size={17} /></div>
              <div>
                <div className="panel-kicker">STEP 2</div>
                <h2>监控目标</h2>
              </div>
            </div>
            <div className="target-grid">
              {targets.map((target) => {
                const Icon = target.icon;
                const active = selectedTargets.includes(target.id);
                return (
                  <button className={`target-card ${active ? "is-selected" : ""}`} type="button" key={target.id} onClick={() => toggleTarget(target.id)}>
                    <span className="target-icon"><Icon size={17} /></span>
                    <strong>{target.label}</strong>
                    <span>{target.description}</span>
                  </button>
                );
              })}
            </div>
          </section>

          <section className="panel wizard-section">
            <div className="wizard-section-heading">
              <div className="section-icon"><Code2 size={17} /></div>
              <div>
                <div className="panel-kicker">STEP 3</div>
                <h2>抓取方式</h2>
              </div>
            </div>
            <div className="method-grid" role="radiogroup" aria-label="抓取方式">
              {extractionMethods.map((method) => {
                const Icon = method.icon;
                return (
                  <button
                    className={`method-option ${extractionMethod === method.id ? "is-selected" : ""}`}
                    type="button"
                    key={method.id}
                    onClick={() => { setExtractionMethod(method.id); resetSaveState(); }}
                    aria-pressed={extractionMethod === method.id}
                  >
                    <Icon size={17} />
                    <strong>{method.label}</strong>
                    <span>{method.description}</span>
                  </button>
                );
              })}
            </div>
          </section>

          <section className="panel wizard-section">
            <div className="wizard-section-heading">
              <div className="section-icon"><BellRing size={17} /></div>
              <div>
                <div className="panel-kicker">STEP 4</div>
                <h2>监控频率与通知渠道</h2>
              </div>
            </div>
            <div className="settings-grid">
              <div>
                <label className="field-label" htmlFor="frequency">监控频率</label>
                <select id="frequency" className="select-input" value={frequency} onChange={(event) => { setFrequency(event.target.value); resetSaveState(); }}>
                  {frequencies.map((item) => <option key={item}>{item}</option>)}
                </select>
              </div>
              <div className="channel-list" aria-label="通知渠道">
                {notificationChannels.map((channel) => (
                  <label className="check-row" key={channel}>
                    <input type="checkbox" checked={channels.includes(channel)} onChange={() => toggleChannel(channel)} />
                    <span>{channel}</span>
                  </label>
                ))}
              </div>
            </div>
          </section>
        </section>

        <aside className="panel wizard-review" aria-label="监控任务摘要">
          <div className="panel-kicker">SUMMARY</div>
          <h2>任务摘要</h2>
          <dl>
            <div><dt>目标</dt><dd>{targetUrl || "未填写"}</dd></div>
            <div><dt>监控目标</dt><dd>{selectedTargetLabels.join("、")}</dd></div>
            <div><dt>抓取方式</dt><dd>{selectedMethod.label}</dd></div>
            <div><dt>监控频率</dt><dd>{frequency}</dd></div>
            <div><dt>通知渠道</dt><dd>{channels.join("、")}</dd></div>
          </dl>
          <button className="primary-button review-save-button" type="button" onClick={saveMonitor} disabled={saveState === "saving"}>
            <Save size={17} /> {saveState === "saving" ? "正在保存…" : "保存监控"}
          </button>
          {saveMessage ? (
            <div className={`draft-confirmation ${saveState === "error" ? "is-error" : ""}`} role="status">
              <CheckCircle2 size={16} />
              <span>{saveMessage}</span>
            </div>
          ) : null}
          {!saved && saveState === "idle" ? <p className="save-hint">保存到真实后端需要先登录 API；未登录时不会丢失当前配置。</p> : null}
        </aside>
      </div>
    </main>
  );
}
