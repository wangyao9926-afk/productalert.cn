import { Menu, Plus, Search, SlidersHorizontal } from "lucide-react";
import { Link } from "react-router-dom";
import { WorkspaceSwitcher } from "./WorkspaceSwitcher";

type TopBarProps = {
  onCreateMonitor: () => void;
  onToggleNavigation: () => void;
};

export function TopBar({ onCreateMonitor, onToggleNavigation }: TopBarProps) {
  return (
    <header className="top-bar">
      <button className="mobile-menu-button" type="button" onClick={onToggleNavigation} aria-label="打开导航">
        <Menu size={18} aria-hidden="true" />
      </button>
      <WorkspaceSwitcher />
      <div className="top-bar-divider" aria-hidden="true" />
      <div className="global-search">
        <Search size={16} aria-hidden="true" />
        <input type="search" placeholder="搜索品牌、产品或变化记录" aria-label="搜索品牌、产品或变化记录" />
        <kbd>⌘ K</kbd>
      </div>
      <div className="top-bar-actions">
        <Link className="button button-secondary api-login-link" to="/login">
          <span>登录 API</span>
        </Link>
        <button className="button button-secondary filter-shortcut" type="button" aria-label="打开快捷筛选">
          <SlidersHorizontal size={15} aria-hidden="true" />
          <span>快捷筛选</span>
        </button>
        <button className="button button-primary" type="button" onClick={onCreateMonitor}>
          <Plus size={16} aria-hidden="true" />
          <span>新建监控</span>
        </button>
        <button className="account-button" type="button" aria-label="打开账户菜单">
          <span className="avatar">研</span>
          <span className="account-copy">
            <strong>运营研究员</strong>
            <small>个人账号</small>
          </span>
        </button>
      </div>
    </header>
  );
}
