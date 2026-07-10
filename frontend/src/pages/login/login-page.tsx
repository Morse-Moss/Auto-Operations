import {
  ArrowRightOutlined,
  CheckCircleOutlined,
  DatabaseOutlined,
  LockOutlined,
  SafetyCertificateOutlined,
  UserOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Col,
  ConfigProvider,
  Form,
  Input,
  Row,
  Segmented,
  Space,
  Typography,
  theme,
} from "antd";
import { type FormEvent, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";

import { useAuth } from "../../hooks/use-auth";

const { Title, Text, Paragraph } = Typography;

type AuthMode = "login" | "register";

const credentialsSchema = z.object({
  username: z
    .string()
    .trim()
    .min(3, "账号至少 3 个字符")
    .max(80, "账号不能超过 80 个字符"),
  password: z
    .string()
    .min(6, "密码至少 6 个字符")
    .max(128, "密码不能超过 128 个字符"),
});

const loginTheme = {
  algorithm: theme.defaultAlgorithm,
  token: {
    colorPrimary: "#ff2442",
    colorInfo: "#2563eb",
    colorSuccess: "#16a34a",
    colorBgBase: "#f8f5f1",
    colorBgContainer: "#ffffff",
    colorBgElevated: "#ffffff",
    colorText: "#172033",
    colorTextSecondary: "#667085",
    colorBorder: "#d8dee9",
    colorBorderSecondary: "#eceff4",
    borderRadius: 8,
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
  },
  components: {
    Button: {
      borderRadius: 8,
      controlHeightLG: 48,
      primaryShadow: "0 12px 22px rgba(255, 36, 66, 0.2)",
    },
    Card: {
      colorBgContainer: "#ffffff",
      colorBorderSecondary: "#e5e9f0",
      borderRadiusLG: 8,
    },
    Form: {
      labelColor: "#344054",
      verticalLabelPadding: "0 0 8px",
    },
    Input: {
      activeBorderColor: "#ff2442",
      activeShadow: "0 0 0 3px rgba(255, 36, 66, 0.12)",
      colorBgContainer: "#ffffff",
      colorBorder: "#cfd7e3",
      hoverBorderColor: "#ff6b7d",
    },
    Segmented: {
      itemActiveBg: "#ffffff",
      itemColor: "#667085",
      itemHoverBg: "#ffffff",
      itemHoverColor: "#172033",
      itemSelectedBg: "#ffffff",
      itemSelectedColor: "#ff2442",
      trackBg: "#f1f3f7",
    },
  },
};

const platformPoints = [
  "账号矩阵",
  "内容库",
  "草稿工坊",
  "发布中心",
];

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

export function LoginPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mode, setMode] = useState<AuthMode>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event?: FormEvent<HTMLFormElement>) {
    if (event) event.preventDefault();
    setError(null);

    const parsed = credentialsSchema.safeParse({ username, password });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "请检查账号和密码。");
      return;
    }

    if (mode === "register" && password !== confirmPassword) {
      setError("两次输入的密码不一致。");
      return;
    }

    setIsSubmitting(true);
    try {
      if (mode === "login") {
        await auth.login(parsed.data);
      } else {
        const trimmedInviteCode = inviteCode.trim();
        await auth.register({
          ...parsed.data,
          ...(trimmedInviteCode ? { invite_code: trimmedInviteCode } : {}),
        });
      }
      const from = (
        location.state as { from?: { pathname?: string } } | null
      )?.from?.pathname;
      navigate(from || "/platform-select", { replace: true });
    } catch (caughtError) {
      setError(
        errorMessage(
          caughtError,
          mode === "login"
            ? "账号不存在或密码错误，请检查后重试。"
            : "注册失败，该平台账号可能已存在。"
        )
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <ConfigProvider theme={loginTheme}>
      <div
        style={{
          minHeight: "100vh",
          background:
            "radial-gradient(circle at 18% 18%, rgba(255, 36, 66, 0.12), transparent 28%), radial-gradient(circle at 84% 12%, rgba(22, 163, 74, 0.12), transparent 24%), linear-gradient(135deg, #fbf7f2 0%, #f7faf8 46%, #eef4fb 100%)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "40px 24px",
        }}
      >
        <Row
          gutter={[48, 28]}
          align="middle"
          style={{ maxWidth: 1120, width: "100%" }}
        >
          <Col xs={24} lg={13}>
            <div style={{ maxWidth: 560 }}>
              <Space align="center" size={14} style={{ marginBottom: 36 }}>
                <div
                  style={{
                    width: 48,
                    height: 48,
                    borderRadius: 8,
                    background: "#ff2442",
                    color: "#fff",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 21,
                    fontWeight: 800,
                    boxShadow: "0 16px 32px rgba(255, 36, 66, 0.22)",
                  }}
                >
                  X
                </div>
                <div>
                  <Text
                    style={{
                      color: "#667085",
                      display: "block",
                      fontSize: 12,
                      fontWeight: 600,
                      letterSpacing: 0,
                    }}
                  >
                    XHS OPERATIONS PLATFORM
                  </Text>
                  <Text strong style={{ color: "#172033", fontSize: 18 }}>
                    小红书智能运营工作台
                  </Text>
                </div>
              </Space>

              <Title
                level={1}
                style={{
                  color: "#101828",
                  fontSize: "clamp(34px, 5vw, 54px)",
                  lineHeight: 1.12,
                  margin: "0 0 20px",
                  fontWeight: 800,
                }}
              >
                把小红书运营流程，收进一个清晰的工作台。
              </Title>
              <Paragraph
                style={{
                  color: "#475467",
                  fontSize: 17,
                  lineHeight: 1.8,
                  marginBottom: 30,
                  maxWidth: 520,
                }}
              >
                从笔记发现、素材整理到草稿协作和发布任务，统一在同一个后台入口完成。
              </Paragraph>

              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 10,
                  marginBottom: 34,
                }}
              >
                {platformPoints.map((item) => (
                  <span
                    key={item}
                    style={{
                      alignItems: "center",
                      background: "rgba(255, 255, 255, 0.72)",
                      border: "1px solid rgba(216, 222, 233, 0.92)",
                      borderRadius: 8,
                      color: "#344054",
                      display: "inline-flex",
                      fontSize: 14,
                      fontWeight: 600,
                      gap: 8,
                      minHeight: 34,
                      padding: "7px 12px",
                    }}
                  >
                    <CheckCircleOutlined style={{ color: "#16a34a" }} />
                    {item}
                  </span>
                ))}
              </div>

              <div
                style={{
                  borderLeft: "3px solid #ff2442",
                  color: "#667085",
                  fontSize: 14,
                  lineHeight: 1.8,
                  paddingLeft: 16,
                  maxWidth: 520,
                }}
              >
                生产环境建议使用管理员发放的邀请码注册；已有账号可直接登录进入平台选择页。
              </div>
            </div>
          </Col>

          <Col xs={24} lg={11}>
            <Card
              style={{
                border: "1px solid #e5e9f0",
                borderRadius: 8,
                boxShadow: "0 28px 70px rgba(16, 24, 40, 0.14)",
                maxWidth: 480,
                marginLeft: "auto",
              }}
              styles={{
                body: { padding: "32px" },
              }}
            >
              <Space direction="vertical" size={6} style={{ width: "100%" }}>
                <Space align="center" size={10}>
                  <div
                    style={{
                      alignItems: "center",
                      background: "#fff0f2",
                      borderRadius: 8,
                      color: "#ff2442",
                      display: "flex",
                      height: 34,
                      justifyContent: "center",
                      width: 34,
                    }}
                  >
                    <LockOutlined />
                  </div>
                  <Text strong style={{ color: "#172033", fontSize: 20 }}>
                    {mode === "login" ? "登录工作台" : "创建平台账号"}
                  </Text>
                </Space>
                <Text style={{ color: "#667085", fontSize: 13 }}>
                  {mode === "login"
                    ? "使用平台账号进入后台。"
                    : "请输入账号信息和管理员邀请码。"}
                </Text>
              </Space>

              <div style={{ margin: "24px 0" }}>
                <Segmented
                  value={mode}
                  onChange={(val) => {
                    setMode(val as AuthMode);
                    setError(null);
                  }}
                  options={[
                    { label: "登录", value: "login" },
                    { label: "注册", value: "register" },
                  ]}
                  block
                  size="large"
                />
              </div>

              <form onSubmit={handleSubmit}>
                <Form layout="vertical" component="div" requiredMark={false}>
                  <Form.Item label="平台账号" style={{ marginBottom: 16 }}>
                    <Input
                      prefix={<UserOutlined style={{ color: "#98a2b3" }} />}
                      placeholder="请输入账号"
                      autoComplete="username"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      size="large"
                      style={{ height: 46 }}
                    />
                  </Form.Item>

                  <Form.Item label="密码" style={{ marginBottom: 16 }}>
                    <Input.Password
                      prefix={<LockOutlined style={{ color: "#98a2b3" }} />}
                      placeholder="请输入密码"
                      autoComplete={
                        mode === "login" ? "current-password" : "new-password"
                      }
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      size="large"
                      style={{ height: 46 }}
                    />
                  </Form.Item>

                  {mode === "register" && (
                    <>
                      <Form.Item label="确认密码" style={{ marginBottom: 16 }}>
                        <Input.Password
                          prefix={<LockOutlined style={{ color: "#98a2b3" }} />}
                          placeholder="请再次输入密码"
                          autoComplete="new-password"
                          value={confirmPassword}
                          onChange={(e) => setConfirmPassword(e.target.value)}
                          size="large"
                          style={{ height: 46 }}
                        />
                      </Form.Item>
                      <Form.Item label="邀请码" style={{ marginBottom: 16 }}>
                        <Input
                          prefix={
                            <SafetyCertificateOutlined
                              style={{ color: "#98a2b3" }}
                            />
                          }
                          placeholder="请输入管理员发放的邀请码"
                          value={inviteCode}
                          onChange={(e) => setInviteCode(e.target.value)}
                          size="large"
                          style={{ height: 46 }}
                        />
                      </Form.Item>
                    </>
                  )}

                  {error && (
                    <Alert
                      message={error}
                      type="error"
                      showIcon
                      style={{ marginBottom: 16, borderRadius: 8 }}
                    />
                  )}

                  <Button
                    type="primary"
                    htmlType="submit"
                    size="large"
                    block
                    loading={isSubmitting}
                    disabled={auth.isChecking}
                    icon={<ArrowRightOutlined />}
                    iconPosition="end"
                  >
                    {mode === "login" ? "进入运营工作台" : "创建账号并进入"}
                  </Button>
                </Form>
              </form>

              <div
                style={{
                  alignItems: "flex-start",
                  background: "#f8fafc",
                  border: "1px solid #edf1f6",
                  borderRadius: 8,
                  color: "#667085",
                  display: "flex",
                  gap: 10,
                  lineHeight: 1.7,
                  marginTop: 18,
                  padding: "12px 14px",
                  fontSize: 12,
                }}
              >
                <DatabaseOutlined style={{ color: "#2563eb", marginTop: 3 }} />
                <span>
                  {mode === "login"
                    ? "登录成功后会进入平台选择页，再选择小红书工作区。"
                    : "如果没有邀请码，请先联系管理员开通账号。"}
                </span>
              </div>
            </Card>
          </Col>
        </Row>
      </div>
    </ConfigProvider>
  );
}
