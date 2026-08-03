import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { ChangeDetailPage } from "../features/changes/ChangeDetailPage";
import { LoginPage } from "../features/auth/LoginPage";
import { InboxPage } from "../features/inbox/InboxPage";
import { PriceMatrixPage } from "../features/intelligence/PriceMatrixPage";
import { CreateMonitorPage } from "../features/monitors/CreateMonitorPage";
import { MonitorsPage } from "../features/monitors/MonitorsPage";
import { NotificationsPage } from "../features/notifications/NotificationsPage";
import { OperationsPage } from "../features/operations/OperationsPage";
import { OverviewPage } from "../features/overview/OverviewPage";
import { ProductDetailPage } from "../features/products/ProductDetailPage";
import { ProductsPage } from "../features/products/ProductsPage";
import { ReportsPage } from "../features/reports/ReportsPage";
import { SettingsPage } from "../features/settings/SettingsPage";

const routeLabels: Record<string, string> = {
  "/monitors": "监控中心",
  "/inbox": "情报收件箱",
  "/products": "产品库",
  "/notifications": "通知中心",
  "/reports": "报告与趋势",
  "/operations": "运维中心",
  "/settings": "设置",
};

function TemporaryPage() {
  const { pathname } = useLocation();
  const label = routeLabels[pathname] || "页面";
  return (
    <section className="page-state panel" aria-live="polite">
      <span className="eyebrow">正在搭建</span>
      <h1>{label}</h1>
      <p>这一入口已纳入 ProductAlert 工作台架构，功能页面将在对应切片中接入真实数据。</p>
      <Link className="button button-primary" to="/overview">返回总览</Link>
    </section>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/overview" replace />} />
      <Route path="/overview" element={<OverviewPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/monitors" element={<MonitorsPage />} />
      <Route path="/monitors/new" element={<CreateMonitorPage />} />
      <Route path="/inbox" element={<InboxPage />} />
      <Route path="/changes/:id" element={<ChangeDetailPage />} />
      <Route path="/products" element={<ProductsPage />} />
      <Route path="/products/:id" element={<ProductDetailPage />} />
      <Route path="/price-matrix" element={<PriceMatrixPage />} />
      <Route path="/notifications" element={<NotificationsPage />} />
      <Route path="/operations" element={<OperationsPage />} />
      <Route path="/reports" element={<ReportsPage />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="/monitors/:id" element={<TemporaryPage />} />
      <Route path="*" element={<TemporaryPage />} />
    </Routes>
  );
}
