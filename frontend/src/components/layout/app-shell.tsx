import {
  BellOutlined,
  ControlOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MoonOutlined,
  RobotOutlined,
  ScheduleOutlined,
  SettingOutlined,
  SunOutlined,
  UserOutlined,
  WalletOutlined,
} from "@ant-design/icons";
import {
  Avatar,
  Badge,
  Button,
  Col,
  Dropdown,
  Layout,
  List,
  Menu,
  Row,
  Space,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import type { MenuProps } from "antd";
import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";

import { useThemeMode } from "../../app/providers";
import { useAuth } from "../../hooks/use-auth";
import { useUsageBalance } from "../../hooks/use-usage-balance";
import { fetchNotifications, markAllNotificationsRead, markNotificationRead } from "../../lib/api";
import { getPlatformIdFromPath, getPlatformNavItems, getPlatformSelectedNavPath } from "../../platform-core/registry/platform-sections";
import type { AppNotification } from "../../types";

const { Sider, Header, Content } = Layout;
const { Title, Text } = Typography;

const footerNavItems: MenuProps["items"] = [
  { key: "/tasks", icon: <ScheduleOutlined />, label: "任务中心" },
];

const adminFooterNavItems: MenuProps["items"] = [
  { key: "/models", icon: <RobotOutlined />, label: "模型配置" },
  { key: "/settings", icon: <SettingOutlined />, label: "设置" },
  { key: "/admin", icon: <ControlOutlined />, label: "Beta 管理" },
];

const roleLabels: Record<string, string> = {
  admin: "管理员",
  user: "体验官",
};

const userStatusLabels: Record<string, string> = {
  active: "账号启用",
  disabled: "账号停用",
};

const tenantStatusLabels: Record<string, string> = {
  active: "租户正常",
  suspended: "租户冻结",
};

const membershipRoleLabels: Record<string, string> = {
  owner: "空间所有者",
  member: "成员",
  admin: "空间管理员",
};

function levelColor(level: string): string {
  if (level === "error") return "#ef4444";
  if (level === "warning") return "#eab308";
  return "#6b7280";
}

function statusTagColor(status?: string | null) {
  if (status === "active") return "success";
  if (status === "suspended" || status === "disabled") return "error";
  return "default";
}

function formatCredits(value: number | null) {
  return value === null ? "加载中" : value.toLocaleString("zh-CN");
}

export function AppShell() {
  const auth = useAuth();
  const usage = useUsageBalance();
  const { mode: themeMode, toggle: toggleTheme } = useThemeMode();
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [isNarrowViewport, setIsNarrowViewport] = useState(() => (
    typeof window === "undefined" ? false : window.innerWidth < 768
  ));
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);

  const isDark = themeMode === "dark";
  const palette = isDark
    ? {
        appBg: "#0b1118",
        panel: "#111827",
        panelAlt: "#162033",
        sider: "#071626",
        header: "#111827",
        border: "#263244",
        text: "#e5edf8",
        muted: "#93a4b8",
        subtle: "#61708a",
        brand: "#2f7df6",
        brandSoft: "rgba(47, 125, 246, 0.16)",
        unread: "rgba(47, 125, 246, 0.12)",
      }
    : {
        appBg: "#f4f7fb",
        panel: "#ffffff",
        panelAlt: "#f8fafc",
        sider: "#ffffff",
        header: "#ffffff",
        border: "#dce4ef",
        text: "#111827",
        muted: "#667085",
        subtle: "#98a2b3",
        brand: "#1f6feb",
        brandSoft: "rgba(31, 111, 235, 0.1)",
        unread: "#eff6ff",
      };

  const username = auth.user?.username ?? "用户";
  const role = auth.user?.role ?? "user";
  const userStatus = auth.user?.status ?? "active";
  const roleLabel = roleLabels[role] ?? role;
  const userStatusLabel = userStatusLabels[userStatus] ?? userStatus;
  const tenant = usage.balance?.tenant;
  const membership = usage.balance?.membership;
  const tenantName = tenant?.name ?? (usage.isLoading ? "租户加载中" : "未绑定租户");
  const tenantStatus = tenant?.status ?? "unknown";
  const tenantStatusLabel = tenantStatusLabels[tenantStatus] ?? tenantStatus;
  const membershipRole = membership ? (membershipRoleLabels[membership.role] ?? membership.role) : "成员";
  const creditsRemaining = usage.bucketRemaining("credits");
  const userInitial = username.slice(0, 1).toUpperCase();

  const loadNotifications = useCallback(async () => {
    try {
      const res = await fetchNotifications({ page_size: 20 });
      setNotifications(res.items);
      setUnreadCount(res.items.filter((n) => !n.read).length);
    } catch {
      // Notification failures should not block the workspace shell.
    }
  }, []);

  useEffect(() => {
    void loadNotifications();
    const timer = setInterval(() => void loadNotifications(), 30_000);
    return () => clearInterval(timer);
  }, [loadNotifications]);

  useEffect(() => {
    const updateViewport = () => setIsNarrowViewport(window.innerWidth < 768);
    updateViewport();
    window.addEventListener("resize", updateViewport);
    return () => window.removeEventListener("resize", updateViewport);
  }, []);

  const handleMarkRead = async (id: number) => {
    await markNotificationRead(id);
    void loadNotifications();
  };
  const handleMarkAllRead = async () => {
    await markAllNotificationsRead();
    void loadNotifications();
  };
  const handleMenuClick: MenuProps["onClick"] = ({ key }) => {
    navigate(key);
  };
  const selectedKeys = [getPlatformSelectedNavPath(location.pathname)];
  const platformId = getPlatformIdFromPath(location.pathname);
  const isAdmin = role === "admin";
  const mainNavItems = getPlatformNavItems(platformId, { includeAdminOnly: isAdmin });
  const footerItems: MenuProps["items"] = auth.user?.role === "admin"
    ? [...(footerNavItems ?? []), ...(adminFooterNavItems ?? [])]
    : footerNavItems;

  const accountDropdownContent = (
    <div
      style={{
        width: 280,
        padding: 14,
        background: palette.panel,
        border: `1px solid ${palette.border}`,
        borderRadius: 8,
        boxShadow: isDark ? "0 14px 36px rgba(0,0,0,.35)" : "0 14px 36px rgba(15,23,42,.12)",
      }}
    >
      <Space align="start" size={10} style={{ width: "100%" }}>
        <Avatar size={36} icon={<UserOutlined />} style={{ background: palette.brand, flexShrink: 0 }}>
          {userInitial}
        </Avatar>
        <div style={{ minWidth: 0, flex: 1 }}>
          <Text strong ellipsis style={{ display: "block", color: palette.text }}>
            {username}
          </Text>
          <Space size={6} wrap style={{ marginTop: 6 }}>
            <Tag color={role === "admin" ? "blue" : "default"} style={{ marginInlineEnd: 0 }}>
              {roleLabel}
            </Tag>
            <Tag color={statusTagColor(userStatus)} style={{ marginInlineEnd: 0 }}>
              {userStatusLabel}
            </Tag>
          </Space>
        </div>
      </Space>
      <div style={{ marginTop: 14, padding: 10, background: palette.panelAlt, borderRadius: 8 }}>
        <Text type="secondary" style={{ display: "block", fontSize: 12 }}>
          当前租户
        </Text>
        <Text strong ellipsis style={{ display: "block", color: palette.text, marginTop: 2 }}>
          {tenantName}
        </Text>
        <Space size={6} wrap style={{ marginTop: 8 }}>
          <Tag color={statusTagColor(tenantStatus)} style={{ marginInlineEnd: 0 }}>
            {tenantStatusLabel}
          </Tag>
          <Tag style={{ marginInlineEnd: 0 }}>{membershipRole}</Tag>
          <Tag color="processing" style={{ marginInlineEnd: 0 }}>
            积分 {formatCredits(creditsRemaining)}
          </Tag>
        </Space>
      </div>
      <Button
        block
        icon={<LogoutOutlined />}
        onClick={() => void auth.logout()}
        style={{ marginTop: 12 }}
      >
        退出登录
      </Button>
    </div>
  );

  const notificationDropdownContent = (
    <div
      style={{
        width: 360,
        background: palette.panel,
        borderRadius: 8,
        border: `1px solid ${palette.border}`,
        overflow: "hidden",
        boxShadow: isDark ? "0 14px 36px rgba(0,0,0,.35)" : "0 14px 36px rgba(15,23,42,.12)",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "12px 16px",
          borderBottom: `1px solid ${palette.border}`,
        }}
      >
        <Text strong style={{ fontSize: 14, color: palette.text }}>
          通知
        </Text>
        {unreadCount > 0 && (
          <Button type="link" size="small" onClick={() => void handleMarkAllRead()}>
            全部已读
          </Button>
        )}
      </div>
      <div style={{ maxHeight: 400, overflowY: "auto" }}>
        {notifications.length === 0 ? (
          <div style={{ padding: "32px 16px", textAlign: "center", color: palette.muted }}>暂无通知</div>
        ) : (
          <List
            dataSource={notifications}
            renderItem={(n) => (
              <List.Item
                key={n.id}
                style={{
                  padding: "10px 16px",
                  cursor: n.read ? "default" : "pointer",
                  background: n.read ? "transparent" : palette.unread,
                  borderBottom: `1px solid ${palette.border}`,
                }}
                onClick={() => !n.read && void handleMarkRead(n.id)}
              >
                <List.Item.Meta
                  avatar={
                    <span
                      style={{
                        display: "inline-block",
                        width: 8,
                        height: 8,
                        borderRadius: "50%",
                        background: levelColor(n.level),
                        marginTop: 6,
                      }}
                    />
                  }
                  title={<Text style={{ fontSize: 13, color: palette.text }}>{n.title}</Text>}
                  description={
                    <div>
                      {n.body && (
                        <Text type="secondary" style={{ fontSize: 12, display: "block" }}>
                          {n.body}
                        </Text>
                      )}
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {new Date(n.created_at).toLocaleString("zh-CN")}
                      </Text>
                    </div>
                  }
                />
              </List.Item>
            )}
          />
        )}
      </div>
    </div>
  );

  const shellCollapsed = collapsed || isNarrowViewport;
  const siderWidth = shellCollapsed ? 64 : 220;

  return (
    <Layout style={{ minHeight: "100vh", background: palette.appBg }}>
      <Sider
        collapsed={shellCollapsed}
        width={220}
        collapsedWidth={64}
        theme={isDark ? "dark" : "light"}
        trigger={null}
        style={{
          height: "100vh",
          position: "fixed",
          left: 0,
          top: 0,
          bottom: 0,
          borderRight: `1px solid ${palette.border}`,
          overflow: "hidden",
          background: palette.sider,
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
          <div
            style={{
              padding: shellCollapsed ? "14px 0" : "14px 14px",
              display: "flex",
              alignItems: "center",
              justifyContent: shellCollapsed ? "center" : "space-between",
              borderBottom: `1px solid ${palette.border}`,
              flexShrink: 0,
              cursor: "pointer",
              background: palette.sider,
            }}
            onClick={() => navigate("/platform-select")}
          >
            <Space align="center" size={shellCollapsed ? 0 : 10} style={{ minWidth: 0 }}>
              <div
                aria-hidden="true"
                style={{
                  width: 30,
                  height: 30,
                  borderRadius: 8,
                  background: "#fff",
                  border: `1px solid ${isDark ? "rgba(255,255,255,0.14)" : "rgba(31,111,235,0.12)"}`,
                  boxShadow: isDark ? "0 8px 20px rgba(31,111,235,.12)" : "0 8px 20px rgba(31,111,235,.16)",
                  flexShrink: 0,
                  overflow: "hidden",
                }}
              >
                <img src="/logo.png" alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
              </div>
              {!shellCollapsed && (
                <div style={{ minWidth: 0 }}>
                  <Text strong ellipsis style={{ display: "block", color: palette.text, fontSize: 13, lineHeight: "18px" }}>
                    拓效自动化运营系统
                  </Text>
                  <Text ellipsis style={{ display: "block", color: palette.muted, fontSize: 11, lineHeight: "16px" }}>
                    Tavix Beta 多租户工作台
                  </Text>
                </div>
              )}
            </Space>
            {!shellCollapsed && (
              <Tooltip title="收起侧栏">
                <Button
                  type="text"
                  size="small"
                  icon={<MenuFoldOutlined />}
                  onClick={(e) => {
                    e.stopPropagation();
                    setCollapsed(true);
                  }}
                  style={{ color: palette.subtle }}
                />
              </Tooltip>
            )}
          </div>
          {shellCollapsed && !isNarrowViewport && (
            <div style={{ textAlign: "center", padding: "6px 0", borderBottom: `1px solid ${palette.border}`, flexShrink: 0 }}>
              <Tooltip title="展开侧栏">
                <Button type="text" size="small" icon={<MenuUnfoldOutlined />} onClick={() => setCollapsed(false)} style={{ color: palette.subtle }} />
              </Tooltip>
            </div>
          )}

          <div style={{ flex: 1, overflowY: "auto", overflowX: "hidden", paddingTop: 8 }}>
            <Menu
              theme={isDark ? "dark" : "light"}
              mode="inline"
              selectedKeys={selectedKeys}
              onClick={handleMenuClick}
              items={mainNavItems}
              style={{ borderRight: 0, background: palette.sider }}
            />
          </div>

          <div style={{ flexShrink: 0, borderTop: `1px solid ${palette.border}`, background: palette.sider }}>
            <Menu
              theme={isDark ? "dark" : "light"}
              mode="inline"
              selectedKeys={selectedKeys}
              onClick={handleMenuClick}
              items={footerItems}
              style={{ borderRight: 0, background: palette.sider }}
            />
            <div
              style={{
                padding: shellCollapsed ? "10px 0" : "10px 14px",
                borderTop: `1px solid ${palette.border}`,
                display: "flex",
                alignItems: "center",
                gap: 10,
                justifyContent: shellCollapsed ? "center" : "flex-start",
              }}
            >
              <Dropdown dropdownRender={() => accountDropdownContent} trigger={["click"]} placement="topLeft">
                <Avatar size={28} icon={<UserOutlined />} style={{ background: palette.brand, flexShrink: 0, cursor: "pointer", fontSize: 12 }}>
                  {userInitial}
                </Avatar>
              </Dropdown>
              {!shellCollapsed && (
                <>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <Space size={6} style={{ maxWidth: "100%" }}>
                      <Text strong ellipsis style={{ maxWidth: 96, color: palette.text, fontSize: 13 }}>
                        {username}
                      </Text>
                      <Tag color={role === "admin" ? "blue" : "default" } style={{ marginInlineEnd: 0 }}>
                        {roleLabel}
                      </Tag>
                    </Space>
                    <Text ellipsis style={{ display: "block", color: palette.muted, fontSize: 11, lineHeight: "16px" }}>
                      {tenantName} · {formatCredits(creditsRemaining)} 积分
                    </Text>
                  </div>
                  <Tooltip title="退出登录">
                    <Button type="text" icon={<LogoutOutlined />} onClick={() => void auth.logout()} size="small" style={{ color: palette.subtle, flexShrink: 0 }} />
                  </Tooltip>
                </>
              )}
            </div>
          </div>
        </div>
      </Sider>

      <Layout style={{ marginLeft: siderWidth, transition: "margin-left 0.2s", background: palette.appBg }}>
        <Header
          style={{
            padding: isNarrowViewport ? "0 10px" : "0 24px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: isNarrowViewport ? 8 : 16,
            borderBottom: `1px solid ${palette.border}`,
            height: 56,
            lineHeight: "56px",
            background: palette.header,
            position: "sticky",
            top: 0,
            zIndex: 10,
          }}
        >
          <div style={{ minWidth: 0, flex: 1, overflow: "hidden" }}>
            <Space size={[8, 4]} wrap style={{ maxWidth: "100%", lineHeight: "normal" }}>
              {!isNarrowViewport && (
                <Text strong style={{ color: palette.text }}>
                  当前身份
                </Text>
              )}
              <Tag color={role === "admin" ? "blue" : "default"} style={{ marginInlineEnd: 0 }}>
                {username} · {roleLabel}
              </Tag>
              {!isNarrowViewport && (
                <Tag color={statusTagColor(userStatus)} style={{ marginInlineEnd: 0 }}>
                  {userStatusLabel}
                </Tag>
              )}
              {!isNarrowViewport && (
                <Tag color={statusTagColor(tenantStatus)} style={{ marginInlineEnd: 0 }}>
                  {tenantName} · {tenantStatusLabel}
                </Tag>
              )}
              <Tag icon={<WalletOutlined />} color="processing" style={{ marginInlineEnd: 0 }}>
                积分 {formatCredits(creditsRemaining)}
              </Tag>
              {usage.error && (
                <Tag color="warning" style={{ marginInlineEnd: 0 }}>
                  积分状态待刷新
                </Tag>
              )}
            </Space>
          </div>
          <Space size={10} align="center" style={{ flexShrink: 0 }}>
            <Tooltip title={themeMode === "dark" ? "切换为日间模式" : "切换为夜间模式"}>
              <Button
                type="text"
                icon={themeMode === "dark" ? <SunOutlined style={{ fontSize: 16 }} /> : <MoonOutlined style={{ fontSize: 16 }} />}
                onClick={toggleTheme}
                style={{ display: "flex", alignItems: "center", justifyContent: "center", color: palette.text }}
              />
            </Tooltip>
            <Dropdown dropdownRender={() => notificationDropdownContent} trigger={["click"]} placement="bottomRight">
              <Badge count={unreadCount} size="small" offset={[-2, 2]}>
                <Button type="text" icon={<BellOutlined style={{ fontSize: 16 }} />} style={{ display: "flex", alignItems: "center", justifyContent: "center", color: palette.text }} />
              </Badge>
            </Dropdown>
            <Dropdown dropdownRender={() => accountDropdownContent} trigger={["click"]} placement="bottomRight">
              <Avatar size={30} style={{ background: palette.brand, fontSize: 12, cursor: "pointer" }}>
                {userInitial}
              </Avatar>
            </Dropdown>
          </Space>
        </Header>
        <Content style={{ padding: isNarrowViewport ? 16 : 24, minHeight: "calc(100vh - 56px)", overflow: "auto", background: palette.appBg, minWidth: 0 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}

export function PageHeader({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: ReactNode }) {
  return (
    <Row justify="space-between" align="top" style={{ marginBottom: 24, gap: 16 }}>
      <Col flex="auto" style={{ minWidth: 0 }}>
        <Text type="secondary" style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: 0 }}>
          {eyebrow}
        </Text>
        <Title level={3} style={{ margin: "4px 0 4px" }}>
          {title}
        </Title>
        <Text type="secondary">{description}</Text>
      </Col>
      {action && <Col flex="none">{action}</Col>}
    </Row>
  );
}
