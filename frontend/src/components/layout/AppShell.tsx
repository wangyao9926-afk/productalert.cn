import { useState } from "react";
import type { ReactNode } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

type AppShellProps = {
  children?: ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <div className="app-shell">
      <Sidebar
        currentPath={location.pathname}
        mobileOpen={mobileNavOpen}
        onNavigate={() => setMobileNavOpen(false)}
      />
      {mobileNavOpen && (
        <button
          className="mobile-scrim"
          type="button"
          aria-label="关闭导航"
          onClick={() => setMobileNavOpen(false)}
        />
      )}
      <div className="workspace">
        <TopBar
          onCreateMonitor={() => navigate("/monitors/new")}
          onToggleNavigation={() => setMobileNavOpen((open) => !open)}
        />
        <main className="workspace-content">{children ?? <Outlet />}</main>
      </div>
    </div>
  );
}
