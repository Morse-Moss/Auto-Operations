import {
  ArrowLeftOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  LockOutlined,
  SafetyCertificateOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Form,
  Input,
  message,
  Row,
  Space,
  Statistic,
  Tag,
  Typography,
} from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { PageHeader } from "../../components/layout/app-shell";
import {
  fetchWechatOfficialContentLibrary,
  fetchWechatOfficialOverview,
  fetchWechatOfficialRedfoxConfig,
  saveWechatOfficialRedfoxConfig,
  validateWechatOfficialRedfoxConfig,
} from "../../lib/api";
import { WechatOfficialContentLibraryPanel } from "./wechat-official-content-library-panel";
import { WechatOfficialDiscoveryPanel } from "./wechat-official-discovery-panel";
import { WechatOfficialDraftWorkbench } from "./wechat-official-draft-workbench";

import type {
  WechatOfficialContentLibraryItem,
  WechatOfficialOverview,
  WechatOfficialRedfoxConfig,
} from "../../types";

const { Paragraph } = Typography;

const cardStyle = { background: "#1f1f1f", borderColor: "#303030" };

const fallbackOverview: WechatOfficialOverview = {
  platform_id: "wechat_official",
  stage: "foundation_ready",
  external_integration_enabled: false,
  research_required_before_integration: true,
  research_topics: ["Redfox 公众号爆文收集", "微信真实发布/群发继续阻断"],
  capabilities: [
    { key: "content.library", label: "公众号内容库", status: "partial", message: "支持 Redfox 爆文入库和候选筛选。" },
    { key: "publish.real_publish", label: "群发发布", status: "blocked", message: "真实发布和群发保持阻断。" },
  ],
  blocked_actions: ["真实授权", "素材上传", "草稿同步", "预览发送", "群发发布"],
};

type WechatOfficialSection = "dashboard" | "accounts" | "discovery" | "library" | "drafts" | "settings";

type RedfoxConfigForm = {
  name: string;
  base_url: string;
  api_key?: string;
};

const SECTION_COPY: Record<WechatOfficialSection, { title: string; description: string }> = {
  dashboard: {
    title: "公众号运营总览",
    description: "汇总 Redfox 配置、爆文候选、内容库和 blocked 动作状态。",
  },
  accounts: {
    title: "公众号账号矩阵",
    description: "查看公众号账号接入状态；真实授权和发布动作仍保持阻断。",
  },
  discovery: {
    title: "公众号爆文发现",
    description: "通过关键词、公众号或文章 URL 收集爆文候选，并把确认后的候选交给内容库。",
  },
  library: {
    title: "公众号内容库",
    description: "管理已入库的公众号文章，补全素材、拆解爆点并生成独立草稿。",
  },
  drafts: {
    title: "公众号草稿工坊",
    description: "基于内容库素材生成和管理公众号二创草稿。",
  },
  settings: {
    title: "Redfox 设置",
    description: "配置和校验 Redfox API Key；Redfox 只作为内容数据源。",
  },
};

function sectionFromPath(pathname: string): WechatOfficialSection {
  const parts = pathname.split("/").filter(Boolean);
  const section = parts[parts.length - 1];
  if (["accounts", "discovery", "library", "drafts", "settings"].includes(section || "")) {
    return section as WechatOfficialSection;
  }
  return "dashboard";
}

function statusColor(status?: string): string {
  if (!status) return "default";
  if (["blocked", "expired", "invalid", "failed", "rejected"].includes(status)) return "red";
  if (["planned", "partial", "pending", "unknown", "analyzing"].includes(status)) return "gold";
  if (["available", "valid", "active", "succeeded", "completed", "shortlisted"].includes(status)) return "green";
  if (["draft_ready"].includes(status)) return "purple";
  return "default";
}

function poolStatus(article: WechatOfficialContentLibraryItem): string {
  return String(article.analysis?.pool_status || article.analysis?.recommendation_status || "candidate");
}

function apiErrorMessage(error: unknown, fallback: string): string {
  if (error && typeof error === "object" && "response" in error) {
    const response = (error as { response?: { data?: { detail?: unknown } } }).response;
    const detail = response?.data?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return error instanceof Error ? error.message : fallback;
}

export function WechatOfficialDashboard() {
  const location = useLocation();
  const currentSection = sectionFromPath(location.pathname);
  const sectionCopy = SECTION_COPY[currentSection];
  const showDashboard = currentSection === "dashboard";
  const showAccounts = currentSection === "accounts";
  const showDiscovery = currentSection === "discovery";
  const showLibrary = currentSection === "library";
  const showDrafts = currentSection === "drafts";
  const showSettings = currentSection === "settings";
  const [overview, setOverview] = useState<WechatOfficialOverview>(fallbackOverview);
  const [redfoxConfig, setRedfoxConfig] = useState<WechatOfficialRedfoxConfig | null>(null);
  const [configured, setConfigured] = useState(false);
  const [contentItems, setContentItems] = useState<WechatOfficialContentLibraryItem[]>([]);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [configForm] = Form.useForm<RedfoxConfigForm>();

  const candidateCount = useMemo(
    () => contentItems.filter((item) => poolStatus(item) === "candidate" || item.is_candidate).length,
    [contentItems],
  );
  const libraryCount = useMemo(
    () => contentItems.filter((item) => ["shortlisted", "analyzing", "draft_ready"].includes(poolStatus(item))).length,
    [contentItems],
  );
  const configuredText = configured ? `已配置 ${redfoxConfig?.masked_api_key || "****"}` : "未配置";

  const refreshWorkspace = useCallback(async () => {
    try {
      const [overviewPayload, configPayload, libraryPayload] = await Promise.all([
        fetchWechatOfficialOverview(),
        fetchWechatOfficialRedfoxConfig(),
        fetchWechatOfficialContentLibrary(),
      ]);
      setOverview(overviewPayload);
      setConfigured(configPayload.configured);
      setRedfoxConfig(configPayload.config);
      setContentItems(libraryPayload.items);
      configForm.setFieldsValue({
        name: configPayload.config?.name ?? "RedFoxHub",
        base_url: configPayload.config?.base_url ?? "https://redfox.hk",
        api_key: "",
      });
      setLoadFailed(false);
    } catch {
      setOverview(fallbackOverview);
      setLoadFailed(true);
    }
  }, [configForm]);

  useEffect(() => {
    void refreshWorkspace();
  }, [refreshWorkspace]);

  async function runAction(actionKey: string, successText: string, action: () => Promise<void>): Promise<void> {
    setBusyAction(actionKey);
    try {
      await action();
      message.success(successText);
    } catch (error) {
      message.error(apiErrorMessage(error, "操作失败，请检查输入和后端状态。"));
    } finally {
      setBusyAction(null);
    }
  }

  const handleSaveConfig = () => runAction("save-config", "Redfox API Key 配置已保存", async () => {
    const values = await configForm.validateFields();
    const response = await saveWechatOfficialRedfoxConfig({
      name: values.name,
      base_url: values.base_url,
      api_key: String(values.api_key || "").trim() || undefined,
    });
    setConfigured(response.configured);
    setRedfoxConfig(response.config);
    configForm.setFieldValue("api_key", "");
  });

  const handleValidateConfig = () => runAction("validate-config", "Redfox 配置校验完成", async () => {
    const response = await validateWechatOfficialRedfoxConfig();
    setRedfoxConfig(response.config);
    setConfigured(Boolean(response.config?.has_api_key));
    if (!response.ok) throw new Error(response.message);
  });

  return (
    <div>
      <PageHeader
        eyebrow="运营中台 / 微信公众号"
        title={sectionCopy.title}
        description={sectionCopy.description}
        action={(
          <Space>
            <Tag color="red">发布/群发 blocked</Tag>
            <Button icon={<SyncOutlined />} loading={busyAction === "refresh"} onClick={() => runAction("refresh", "页面已刷新", refreshWorkspace)}>刷新</Button>
            <Link to="/platform-select"><Button icon={<ArrowLeftOutlined />}>平台中心</Button></Link>
          </Space>
        )}
      />

      {loadFailed ? (
        <Alert showIcon type="warning" style={{ marginBottom: 16 }} message="公众号数据读取失败" description="已保留本地 fallback 状态。请确认已登录主系统且后端服务可用。" />
      ) : null}

      <Alert
        showIcon
        type="info"
        style={{ marginBottom: 16 }}
        message="Redfox 是内容数据源，不是公众号发布通道"
        description="爆文发现只收集候选并交给内容库；内容库和草稿工坊各自处理素材、拆解与草稿能力。真实授权、素材上传、草稿同步、预览发送、群发发布没有可执行入口。"
      />

      <Row gutter={[16, 16]}>
        {showDashboard ? (
          <>
            <Col xs={24} md={8} xl={6}><Card style={cardStyle}><Statistic title="Redfox" value={configuredText} prefix={<SafetyCertificateOutlined />} /></Card></Col>
            <Col xs={24} md={8} xl={6}><Card style={cardStyle}><Statistic title="爆文候选" value={candidateCount} prefix={<DatabaseOutlined />} /></Card></Col>
            <Col xs={24} md={8} xl={6}><Card style={cardStyle}><Statistic title="内容库" value={libraryCount} prefix={<FileTextOutlined />} /></Card></Col>
            <Col xs={24} md={8} xl={6}><Card style={cardStyle}><Statistic title="Blocked actions" value={overview.blocked_actions.length} prefix={<LockOutlined />} /></Card></Col>
            <Col xs={24}>
              <Collapse
                items={[
                  {
                    key: "debug",
                    label: "高级调试：微信后台 session / credential / proxy / upstream JSON",
                    children: (
                      <Space direction="vertical" style={{ width: "100%" }}>
                        <Alert showIcon type="warning" message="调试能力已从主流程移出" description="旧版后台 session、credential、proxy、searchbiz/appmsgpublish JSON、HTML/CGI/comments payload 入口保留为内部联调能力；本轮默认主路径使用 Redfox。" />
                        <Space wrap>
                          {overview.blocked_actions.map((action) => <Tag key={action} color="red">{action}</Tag>)}
                          {overview.capabilities.map((capability) => <Tag key={capability.key} color={statusColor(capability.status)}>{capability.label}: {capability.status}</Tag>)}
                        </Space>
                      </Space>
                    ),
                  },
                ]}
              />
            </Col>
          </>
        ) : null}

        {showAccounts ? (
          <Col xs={24}>
            <Card title="公众号账号矩阵" style={cardStyle}>
              <Alert
                showIcon
                type="warning"
                message="真实公众号授权仍保持阻断"
                description="当前账号矩阵只展示接入状态和安全边界；真实授权、素材上传、草稿同步、预览发送、群发发布没有可执行入口。"
                style={{ marginBottom: 16 }}
              />
              <Row gutter={[16, 16]}>
                <Col xs={24} md={8}><Card size="small" style={cardStyle}><Statistic title="Redfox 数据源" value={configuredText} prefix={<SafetyCertificateOutlined />} /></Card></Col>
                <Col xs={24} md={8}><Card size="small" style={cardStyle}><Statistic title="账号授权" value="blocked" prefix={<LockOutlined />} /></Card></Col>
                <Col xs={24} md={8}><Card size="small" style={cardStyle}><Statistic title="Blocked actions" value={overview.blocked_actions.length} prefix={<LockOutlined />} /></Card></Col>
              </Row>
            </Card>
          </Col>
        ) : null}

        {showDiscovery ? (
          <Col xs={24}>
            <WechatOfficialDiscoveryPanel />
          </Col>
        ) : null}

        {showLibrary ? (
          <Col xs={24}>
            <WechatOfficialContentLibraryPanel />
          </Col>
        ) : null}

        {showDrafts ? (
          <Col xs={24}>
            <WechatOfficialDraftWorkbench />
          </Col>
        ) : null}

        {showSettings ? (
          <Col xs={24} xl={8}>
            <Card title="Redfox API 配置" style={cardStyle}>
              <Form form={configForm} layout="vertical" initialValues={{ name: "RedFoxHub", base_url: "https://redfox.hk" }}>
                <Form.Item label="名称" name="name"><Input placeholder="RedFoxHub" /></Form.Item>
                <Form.Item label="Base URL" name="base_url"><Input placeholder="https://redfox.hk" /></Form.Item>
                <Form.Item label="API Key" name="api_key"><Input.Password placeholder="REDFOX_API_KEY；留空不会覆盖已保存 key" /></Form.Item>
              </Form>
              <Space wrap>
                <Button type="primary" loading={busyAction === "save-config"} onClick={handleSaveConfig}>保存 API Key</Button>
                <Button loading={busyAction === "validate-config"} onClick={handleValidateConfig}>校验连接</Button>
                <Tag color={statusColor(redfoxConfig?.status)}>{redfoxConfig?.status || "not_configured"}</Tag>
              </Space>
              <Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
                API Key 仅加密保存在服务端，不返回明文；当前状态：{configuredText}{redfoxConfig?.last_error ? ` / ${redfoxConfig.last_error}` : ""}
              </Paragraph>
            </Card>
          </Col>
        ) : null}
      </Row>
    </div>
  );
}
