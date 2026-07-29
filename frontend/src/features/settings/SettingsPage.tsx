import { useEffect, useMemo, useState } from "react";
import {
  BellRing,
  Database,
  Download,
  KeyRound,
  LockKeyhole,
  Mail,
  RefreshCw,
  Save,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  UserCircle,
  Webhook,
  Workflow,
} from "lucide-react";
import { Link } from "react-router-dom";
import { ApiError, getJson } from "../../api/client";
import { getCurrentUser, type AuthUser } from "../../api/auth";
import type { SystemHealth } from "../../types/api";

type SettingsMode = "live" | "auth-required" | "fallback";

const notificationChannels = [
  { key: "email", label: "邮件", icon: Mail, detail: "适合日报、周报、重要变化归档。", status: "待配置 SMTP / 邮件服务" },
  { key: "webhook", label: "Webhook", icon: Webhook, detail: "适合对接自动化流程、数据仓库、内部系统。", status: "可在监控规则中配置目标 URL" },
  { key: "im", label: "企业微信 / 飞书", icon: BellRing, detail: "适合运营群实时提醒和值班协作。", status: "待接入机器人 Webhook" },
];

const scanDefaults = [
  { label: "默认扫描频率", value: "60 分钟", detail: "新建监控时的默认周期" },
  { label: "页面抓取策略", value: "自动识别", detail: "优先结构化解析，失败后降级文本比对" },
  { label: "变化保留周期", value: "90 天", detail: "用于趋势、审计和误报复盘" },
  { label: "失败重试次数", value: "3 次", detail: "网络、反爬和临时错误的重试上限" },
];

const webhookSettings = [
  { label: "签名校验", value: "待启用", detail: "建议上线前为 Webhook 请求增加签名" },
  { label: "超时限制", value: "10 秒", detail: "避免通知渠道阻塞 worker" },
  { label: "失败重试", value: "指数退避", detail: "失败通知进入重试队列" },
];

const apiKeySettings = [
  { label: "API Key", value: "待生成", detail: "后续用于外部系统读取监控结果" },
  { label: "权限范围", value: "只读 / 管理", detail: "按工作空间和功能模块授权" },
  { label: "最后使用", value: "暂无记录", detail: "上线后记录调用审计" },
];

const securitySettings = [
  { label: "登录保护", value: "已启用", detail: "后端已具备登录失败限流" },
  { label: "会话 Cookie", value: "已启用", detail: "API 请求支持 Cookie 会话" },
  { label: "URL 安全校验", value: "已启用", detail: "监控目标和 Webhook 会做安全校验" },
];

const exportBackup = [
  { label: "产品 CSV", href: "/api/export/products.csv", detail: "导出当前产品库" },
  { label: "通知 CSV", href: "/api/export/notifications.csv", detail: "导出通知队列" },
  { label: "生产备份脚本", href: "#", detail: "使用项目内 backup / restore 脚本" },
];

export function SettingsPage() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [mode, setMode] = useState<SettingsMode>("fallback");
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("设置 API 不可用，当前显示配置骨架");

  const refresh = () => {
    setLoading(true);
    Promise.allSettled([
      getCurrentUser(),
      getJson<SystemHealth>("/api/system/health"),
    ]).then(([userResult, healthResult]) => {
      if (userResult.status === "fulfilled") setUser(userResult.value);
      if (healthResult.status === "fulfilled") setHealth(healthResult.value);

      if (userResult.status === "fulfilled" || healthResult.status === "fulfilled") {
        setMode("live");
        setMessage("真实 API 已连接，当前显示账号和系统配置状态");
        return;
      }

      const reason = userResult.status === "rejected" ? userResult.reason : null;
      if (reason instanceof ApiError && (reason.status === 401 || reason.status === 403)) {
        setMode("auth-required");
        setMessage("请先登录后查看账号和工作空间设置，当前显示配置骨架");
        return;
      }

      setMode("fallback");
      setMessage("设置 API 不可用，当前显示配置骨架");
    }).finally(() => setLoading(false));
  };

  useEffect(refresh, []);

  const workspaceSettings = useMemo(() => ({
    name: "ProductAlert 工作空间",
    domain: "productalert.cn",
    database: health?.database_backend || "unknown",
    queue: health?.queue_backend || "unknown",
  }), [health]);

  const accountSettings = useMemo(() => ({
    email: user?.email || "未登录",
    userId: user?.id ? `#${user.id}` : "N/A",
    lastLogin: user?.last_login_at || "暂无记录",
  }), [user]);

  if (loading) {
    return <div className="page-loading"><RefreshCw size={18} className="spin" /> 正在加载设置中心...</div>;
  }

  return (
    <main className="settings-page">
      <header className="page-header">
        <div>
          <div className="eyebrow">SETTINGS</div>
          <h1>设置中心</h1>
          <p>管理账号、工作空间、通知渠道、扫描默认参数、Webhook、API Key、安全和导出备份入口。</p>
          <div className={`api-status-pill ${mode === "live" ? "success" : "warning"}`}>
            {mode === "live" ? "真实 API" : mode === "auth-required" ? "需要登录" : "演示数据"} · {message}
          </div>
        </div>
        <div className="page-actions">
          <button className="icon-button" type="button" onClick={refresh} aria-label="刷新设置"><RefreshCw size={17} /></button>
          <button className="primary-button" type="button"><Save size={17} /> 保存设置</button>
        </div>
      </header>

      <section className="settings-summary-grid" aria-label="设置摘要">
        <SettingsMetric label="账号" value={accountSettings.email} detail={accountSettings.userId} icon={<UserCircle size={18} />} tone="blue" />
        <SettingsMetric label="工作空间" value={workspaceSettings.name} detail={workspaceSettings.domain} icon={<Workflow size={18} />} tone="purple" />
        <SettingsMetric label="数据库" value={workspaceSettings.database} detail="当前后端数据库" icon={<Database size={18} />} tone="green" />
        <SettingsMetric label="队列" value={workspaceSettings.queue} detail="扫描和通知任务队列" icon={<SlidersHorizontal size={18} />} tone="orange" />
      </section>

      <section className="settings-grid">
        <div className="panel settings-panel">
          <div className="panel-heading">
            <div>
              <div className="panel-kicker">ACCOUNT</div>
              <h2>账号与工作空间</h2>
            </div>
          </div>
          <dl className="metadata-list">
            <div><dt>账号邮箱</dt><dd>{accountSettings.email}</dd></div>
            <div><dt>用户 ID</dt><dd>{accountSettings.userId}</dd></div>
            <div><dt>最近登录</dt><dd>{accountSettings.lastLogin}</dd></div>
            <div><dt>工作空间</dt><dd>{workspaceSettings.name}</dd></div>
            <div><dt>绑定域名</dt><dd>{workspaceSettings.domain}</dd></div>
          </dl>
        </div>

        <aside className="panel settings-panel">
          <div className="panel-heading">
            <div>
              <div className="panel-kicker">SECURITY</div>
              <h2>安全设置</h2>
            </div>
            <span className="tag">securitySettings</span>
          </div>
          <SettingsList items={securitySettings} icon={<ShieldCheck size={16} />} />
        </aside>
      </section>

      <section className="settings-grid">
        <div className="panel settings-panel">
          <div className="panel-heading">
            <div>
              <div className="panel-kicker">CHANNELS</div>
              <h2>通知渠道</h2>
            </div>
            <span className="tag">notificationChannels</span>
          </div>
          <div className="settings-card-list">
            {notificationChannels.map(({ key, label, icon: Icon, detail, status }) => (
              <article className="settings-card" key={key}>
                <Icon size={18} />
                <div>
                  <strong>{label}</strong>
                  <p>{detail}</p>
                  <span>{status}</span>
                </div>
              </article>
            ))}
          </div>
        </div>

        <aside className="panel settings-panel">
          <div className="panel-heading">
            <div>
              <div className="panel-kicker">SCAN DEFAULTS</div>
              <h2>扫描默认参数</h2>
            </div>
            <span className="tag">scanDefaults</span>
          </div>
          <SettingsList items={scanDefaults} icon={<Settings size={16} />} />
        </aside>
      </section>

      <section className="settings-grid">
        <div className="panel settings-panel">
          <div className="panel-heading">
            <div>
              <div className="panel-kicker">WEBHOOK</div>
              <h2>Webhook 设置</h2>
            </div>
            <span className="tag">webhookSettings</span>
          </div>
          <SettingsList items={webhookSettings} icon={<Webhook size={16} />} />
        </div>

        <aside className="panel settings-panel">
          <div className="panel-heading">
            <div>
              <div className="panel-kicker">API KEY</div>
              <h2>API Key</h2>
            </div>
            <span className="tag">apiKeySettings</span>
          </div>
          <SettingsList items={apiKeySettings} icon={<KeyRound size={16} />} />
        </aside>
      </section>

      <section className="panel settings-panel">
        <div className="panel-heading">
          <div>
            <div className="panel-kicker">EXPORT & BACKUP</div>
            <h2>导出与备份</h2>
          </div>
          <span className="tag">exportBackup</span>
        </div>
        <div className="export-grid">
          {exportBackup.map((item) => (
            item.href === "#"
              ? <div className="export-card" key={item.label}><Download size={18} /><strong>{item.label}</strong><span>{item.detail}</span></div>
              : <a className="export-card" href={item.href} target="_blank" rel="noreferrer" key={item.label}><Download size={18} /><strong>{item.label}</strong><span>{item.detail}</span></a>
          ))}
          <Link className="export-card" to="/operations"><LockKeyhole size={18} /><strong>上线检查</strong><span>进入运维中心查看 worker、队列和数据库健康度</span></Link>
        </div>
      </section>
    </main>
  );
}

function SettingsMetric({ label, value, detail, icon, tone }: { label: string; value: string; detail: string; icon: React.ReactNode; tone: string }) {
  return (
    <div className="metric-card settings-summary-card">
      <div className={`metric-icon ${tone}`}>{icon}</div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}

function SettingsList({ items, icon }: { items: Array<{ label: string; value: string; detail: string }>; icon: React.ReactNode }) {
  return (
    <div className="settings-list">
      {items.map((item) => (
        <div className="settings-list-row" key={item.label}>
          <span>{icon}</span>
          <div>
            <strong>{item.label}</strong>
            <small>{item.detail}</small>
          </div>
          <em>{item.value}</em>
        </div>
      ))}
    </div>
  );
}
