import { Button, Space, Spin, Typography } from "antd";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "../../hooks/use-auth";
import { clearAuthTokens } from "../../lib/api";

type RouteGuardProps = {
  children: ReactNode;
};

const { Text } = Typography;

function resetStalledAuthCheck(): void {
  clearAuthTokens();
  window.location.assign("/login");
}

function AuthCheckingScreen() {
  const [showRecovery, setShowRecovery] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setShowRecovery(true), 8000);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "100vh",
        background: "#0a0a0a",
        padding: 24,
      }}
    >
      <Space direction="vertical" align="center" size={16} style={{ textAlign: "center" }}>
        <Spin size="large" />
        <div>
          <Text style={{ display: "block", color: "#f8fafc" }}>正在验证登录状态...</Text>
          {showRecovery && (
            <Text style={{ display: "block", marginTop: 8, color: "rgba(248,250,252,0.68)" }}>
              如果长时间停留，请重新登录。
            </Text>
          )}
        </div>
        {showRecovery && (
          <Button type="primary" onClick={resetStalledAuthCheck}>
            重新登录
          </Button>
        )}
      </Space>
    </div>
  );
}

export function ProtectedRoute({ children }: RouteGuardProps) {
  const location = useLocation();
  const auth = useAuth();

  if (auth.isChecking) {
    return <AuthCheckingScreen />;
  }

  if (!auth.isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}

export function PublicOnlyRoute({ children }: RouteGuardProps) {
  const auth = useAuth();

  if (auth.isChecking) {
    return <AuthCheckingScreen />;
  }

  if (auth.isAuthenticated) {
    return <Navigate to="/platform-select" replace />;
  }

  return <>{children}</>;
}

export function AdminRoute({ children }: RouteGuardProps) {
  const auth = useAuth();

  if (auth.isChecking) {
    return <AuthCheckingScreen />;
  }

  if (!auth.isAuthenticated || auth.user?.role !== "admin") {
    return <Navigate to="/platform-select" replace />;
  }

  return <>{children}</>;
}
