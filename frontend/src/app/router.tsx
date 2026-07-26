import { Suspense, lazy } from "react";
import { Spin } from "antd";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "../components/layout/app-shell";
import { AdminRoute, ProtectedRoute, PublicOnlyRoute } from "../components/ui/protected-route";
import { WECHAT_OFFICIAL_PUBLIC_ENABLED } from "../lib/platforms";
import { LoginPage } from "../pages/login/login-page";

const ComingSoonPage = lazy(() =>
  import("../components/platforms/coming-soon").then((m) => ({ default: m.ComingSoonPage })),
);
const BetaAdminPage = lazy(() =>
  import("../pages/admin/beta-admin-page").then((m) => ({ default: m.BetaAdminPage })),
);
const ModelConfigPage = lazy(() =>
  import("../pages/models/model-config-page").then((m) => ({ default: m.ModelConfigPage })),
);
const PlatformSelectPage = lazy(() =>
  import("../pages/platform-select/platform-select-page").then((m) => ({ default: m.PlatformSelectPage })),
);
const SettingsPage = lazy(() =>
  import("../pages/settings/settings-page").then((m) => ({ default: m.SettingsPage })),
);
const TaskCenterPage = lazy(() =>
  import("../pages/tasks/task-center-page").then((m) => ({ default: m.TaskCenterPage })),
);
const DemoPlatformLibraryPage = lazy(() =>
  import("../pages/demo-platform/demo-library-page").then((m) => ({ default: m.DemoPlatformLibraryPage })),
);
const WechatOfficialAccountsPage = lazy(() =>
  import("../pages/wechat-official/wechat-official-accounts-page").then((m) => ({
    default: m.WechatOfficialAccountsPage,
  })),
);
const WechatOfficialDashboardPage = lazy(() =>
  import("../pages/wechat-official/wechat-official-dashboard").then((m) => ({
    default: m.WechatOfficialDashboardPage,
  })),
);
const WechatOfficialDiscoveryPage = lazy(() =>
  import("../pages/wechat-official/wechat-official-discovery-page").then((m) => ({
    default: m.WechatOfficialDiscoveryPage,
  })),
);
const WechatOfficialDraftsPage = lazy(() =>
  import("../pages/wechat-official/wechat-official-drafts-page").then((m) => ({
    default: m.WechatOfficialDraftsPage,
  })),
);
const WechatOfficialLibraryPage = lazy(() =>
  import("../pages/wechat-official/wechat-official-library-page").then((m) => ({
    default: m.WechatOfficialLibraryPage,
  })),
);
const WechatOfficialSettingsPage = lazy(() =>
  import("../pages/wechat-official/wechat-official-settings-page").then((m) => ({
    default: m.WechatOfficialSettingsPage,
  })),
);
const AutoOpsPage = lazy(() =>
  import("../pages/platforms/xhs/auto-ops-page").then((m) => ({ default: m.AutoOpsPage })),
);
const XhsAccountsPage = lazy(() =>
  import("../pages/platforms/xhs/accounts-page").then((m) => ({ default: m.XhsAccountsPage })),
);
const XhsAnalyticsPage = lazy(() =>
  import("../pages/platforms/xhs/analytics-page").then((m) => ({ default: m.XhsAnalyticsPage })),
);
const XhsBenchmarksPage = lazy(() =>
  import("../pages/platforms/xhs/benchmarks-page").then((m) => ({ default: m.XhsBenchmarksPage })),
);
const XhsDashboard = lazy(() =>
  import("../pages/platforms/xhs/xhs-dashboard").then((m) => ({ default: m.XhsDashboard })),
);
const XhsDataSourcesPage = lazy(() =>
  import("../pages/platforms/xhs/xhs-data-sources-page").then((m) => ({ default: m.XhsDataSourcesPage })),
);
const XhsDraftsPage = lazy(() =>
  import("../pages/platforms/xhs/rewrite-page").then((m) => ({ default: m.XhsDraftsPage })),
);
const XhsKeywordsPage = lazy(() =>
  import("../pages/platforms/xhs/keywords-page").then((m) => ({ default: m.XhsKeywordsPage })),
);
const XhsLibraryPage = lazy(() =>
  import("../pages/platforms/xhs/library-page").then((m) => ({ default: m.XhsLibraryPage })),
);
const XhsImageStudioPage = lazy(() =>
  import("../pages/platforms/xhs/image-studio-page").then((m) => ({ default: m.XhsImageStudioPage })),
);
const XhsPublishPage = lazy(() =>
  import("../pages/platforms/xhs/publish-page").then((m) => ({ default: m.XhsPublishPage })),
);
const XhsVideoStudioPage = lazy(() =>
  import("../pages/platforms/xhs/video-studio-page").then((m) => ({ default: m.XhsVideoStudioPage })),
);
const XhsSectionPage = lazy(() =>
  import("../pages/platforms/xhs/xhs-section-page").then((m) => ({ default: m.XhsSectionPage })),
);

function RouteLoadingFallback() {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "60vh",
      }}
    >
      <Spin size="large" />
    </div>
  );
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <Suspense fallback={<RouteLoadingFallback />}>
        <Routes>
          <Route path="/" element={<Navigate to="/platform-select" replace />} />
          <Route
            path="/login"
            element={
              <PublicOnlyRoute>
                <LoginPage />
              </PublicOnlyRoute>
            }
          />
          <Route
            path="/platform-select"
            element={
              <ProtectedRoute>
                <PlatformSelectPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/platforms/:platformId"
            element={
              <ProtectedRoute>
                <ComingSoonPage />
              </ProtectedRoute>
            }
          />
          <Route
            element={
              <ProtectedRoute>
                <AppShell />
              </ProtectedRoute>
            }
          >
            <Route path="/platforms/demo-platform/library" element={<DemoPlatformLibraryPage />} />
            {WECHAT_OFFICIAL_PUBLIC_ENABLED ? (
              <>
                <Route path="/platforms/wechat-official/dashboard" element={<WechatOfficialDashboardPage />} />
                <Route path="/platforms/wechat-official/accounts" element={<WechatOfficialAccountsPage />} />
                <Route path="/platforms/wechat-official/discovery" element={<WechatOfficialDiscoveryPage />} />
                <Route path="/platforms/wechat-official/library" element={<WechatOfficialLibraryPage />} />
                <Route path="/platforms/wechat-official/drafts" element={<WechatOfficialDraftsPage />} />
                <Route path="/platforms/wechat-official/image-studio" element={<XhsImageStudioPage />} />
                <Route path="/platforms/wechat-official/settings" element={<AdminRoute><WechatOfficialSettingsPage /></AdminRoute>} />
              </>
            ) : (
              <Route path="/platforms/wechat-official/*" element={<Navigate to="/platform-select" replace />} />
            )}
            <Route path="/platforms/xhs/dashboard" element={<XhsDashboard />} />
            <Route path="/platforms/xhs/accounts" element={<XhsAccountsPage />} />
            <Route path="/platforms/xhs/analytics" element={<XhsAnalyticsPage />} />
            <Route path="/platforms/xhs/discovery" element={<Navigate to="/platforms/xhs/crawler?source=realtime" replace />} />
            <Route path="/platforms/xhs/crawler" element={<XhsDataSourcesPage />} />
            <Route path="/platforms/xhs/keywords" element={<XhsKeywordsPage />} />
            <Route path="/platforms/xhs/library" element={<XhsLibraryPage />} />
            <Route path="/platforms/xhs/drafts" element={<XhsDraftsPage />} />
            <Route path="/platforms/xhs/benchmarks" element={<XhsBenchmarksPage />} />
            <Route path="/platforms/xhs/image-studio" element={<XhsImageStudioPage />} />
            <Route path="/platforms/xhs/video-studio" element={<XhsVideoStudioPage />} />
            <Route path="/platforms/xhs/publish" element={<XhsPublishPage />} />
            <Route path="/platforms/xhs/auto-ops" element={<AutoOpsPage />} />
            <Route path="/platforms/xhs/:section" element={<XhsSectionPage />} />
            <Route path="/tasks" element={<TaskCenterPage />} />
            <Route path="/models" element={<AdminRoute><ModelConfigPage /></AdminRoute>} />
            <Route path="/settings" element={<AdminRoute><SettingsPage /></AdminRoute>} />
            <Route path="/admin" element={<AdminRoute><BetaAdminPage /></AdminRoute>} />
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
