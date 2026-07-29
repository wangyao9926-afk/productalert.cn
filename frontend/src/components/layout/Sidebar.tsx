import {
  Activity,
  BellRing,
  Boxes,
  Gauge,
  Inbox,
  LayoutDashboard,
  ListChecks,
  Settings,
} from "lucide-react";
import { NavLink } from "react-router-dom";

type SidebarProps = {
  currentPath: string;
  mobileOpen: boolean;
  onNavigate: () => void;
};

const items = [
  { to: "/overview", label: "总览", icon: LayoutDashboard },
  { to: "/monitors", label: "监控中心", icon: Gauge },
  { to: "/inbox", label: "情报收件箱", icon: Inbox, badge: 3 },
  { to: "/products", label: "产品库", icon: Boxes },
  { to: "/notifications", label: "通知中心", icon: BellRing },
  { to: "/reports", label: "报告与趋势", icon: Activity },
  { to: "/operations", label: "运维中心", icon: ListChecks },
];

export function Sidebar({ currentPath, mobileOpen, onNavigate }: SidebarProps) {
  return (
    <aside className={`side-rail ${mobileOpen ? "is-open" : ""}`} aria-label="主导航">
      <div className="brand-lockup">
        <div className="brand-mark" aria-hidden="true">
          <img className="brand-logo" src="/productalert-logo.svg" alt="" />
        </div>
        <div>
          <strong>ProductAlert</strong>
          <span>productalert.cn</span>
        </div>
      </div>

      <div className="workspace-label">
        <span className="status-dot status-dot-success" />
        <span>我的工作空间</span>
      </div>

      <nav className="primary-nav">
        <span className="nav-section-label">工作台</span>
        {items.map(({ to, label, icon: Icon, badge }) => (
          <NavLink
            key={to}
            to={to}
            onClick={onNavigate}
            className={({ isActive }) => `nav-item ${isActive || currentPath.startsWith(`${to}/`) ? "is-active" : ""}`}
            aria-current={currentPath === to || currentPath.startsWith(`${to}/`) ? "page" : undefined}
          >
            <Icon size={16} strokeWidth={2.2} />
            <span>{label}</span>
            {badge ? <span className="nav-badge">{badge}</span> : null}
          </NavLink>
        ))}
      </nav>

      <div className="side-rail-footer">
        <NavLink
          to="/settings"
          onClick={onNavigate}
          className={({ isActive }) => `nav-item ${isActive ? "is-active" : ""}`}
        >
          <Settings size={16} strokeWidth={2.2} />
          <span>设置</span>
        </NavLink>
        <div className="workspace-health">
          <span className="status-dot status-dot-success" />
          <div>
            <strong>监控运行正常</strong>
            <span>最近检查 2 分钟前</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
