import {
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
  Row,
  Space,
  Statistic,
  Tag,
} from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useAuth } from "../../hooks/use-auth";
import { PlatformReadinessPanel } from "../../platform-core/readiness/platform-readiness-panel";
import { PlatformSectionPage } from "../../platform-core/shell/platform-section-page";
import {
  fetchWechatOfficialContentLibrary,
  fetchWechatOfficialOverview,
  fetchWechatOfficialReadiness,
  fetchWechatOfficialRedfoxConfig,
} from "../../lib/api";

import type {
  WechatOfficialContentLibraryItem,
  WechatOfficialOverview,
  WechatOfficialReadiness,
  WechatOfficialRedfoxConfig,
} from "../../types";
import { buildWechatOfficialReadinessActions } from "./wechat-official-readiness-actions";

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

const fallbackReadiness: WechatOfficialReadiness = {
  summary: { overall_status: "blocked", next_actions: ["配置 Redfox", "采集公众号候选", "从内容库生成草稿"] },
  checks: [
    { key: "redfox.config", label: "Redfox 配置", status: "missing", message: "Redfox 未配置。", action: "去设置页配置 Redfox" },
    { key: "safety.publish", label: "真实发布安全边界", status: "blocked", message: "真实发布、预览发送、群发和素材上传均保持阻断。", action: "需要真实发布时先做风险和 QA 设计" },
  ],
  redfox: { configured: false, status: "missing" },
  sessions: { valid: 0, pending: 0, expired: 0, invalid: 0, total: 0 },
  content: { total: 0, candidate: 0, shortlisted: 0, analyzing: 0, draft_ready: 0, rejected: 0, snapshots: 0, images: 0, comments: 0, metrics: 0 },
  feishu: { configured: false, enabled: false },
  drafts: { count: 0, dry_run_available: true },
  image_studio: { available: true, material_upload_blocked: true },
  safety: { publish_blocked: true, sendall_blocked: true, preview_blocked: true, material_upload_blocked: true, message: "真实发布、预览发送、群发和素材上传均保持阻断。" },
};

function statusColor(status?: string): string {
  if (!status) return "default";
  if (["blocked", "expired", "invalid", "failed", "rejected", "missing"].includes(status)) return "red";
  if (["planned", "partial", "pending", "unknown", "analyzing"].includes(status)) return "gold";
  if (["ready", "available", "valid", "active", "succeeded", "completed", "shortlisted"].includes(status)) return "green";
  if (["draft_ready"].includes(status)) return "purple";
  return "default";
}

function poolStatus(article: WechatOfficialContentLibraryItem): string {
  return String(article.analysis?.pool_status || article.analysis?.recommendation_status || "candidate");
}

export function WechatOfficialDashboardPage() {
  const auth = useAuth();
  const isAdmin = auth.user?.role === "admin";
  const [overview, setOverview] = useState<WechatOfficialOverview>(fallbackOverview);
  const [readiness, setReadiness] = useState<WechatOfficialReadiness>(fallbackReadiness);
  const [configured, setConfigured] = useState(false);
  const [redfoxConfig, setRedfoxConfig] = useState<WechatOfficialRedfoxConfig | null>(null);
  const [contentItems, setContentItems] = useState<WechatOfficialContentLibraryItem[]>([]);
  const [loadFailed, setLoadFailed] = useState(false);
  const [readinessCompatibilityMode, setReadinessCompatibilityMode] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const candidateCount = useMemo(
    () => contentItems.filter((item) => poolStatus(item) === "candidate" || item.is_candidate).length,
    [contentItems],
  );
  const libraryCount = useMemo(
    () => contentItems.filter((item) => ["shortlisted", "analyzing", "draft_ready"].includes(poolStatus(item))).length,
    [contentItems],
  );
  const configuredText = configured ? `已配置 ${redfoxConfig?.masked_api_key || "****"}` : "未配置";
  const readinessActions = useMemo(() => buildWechatOfficialReadinessActions(readiness, { includeAdminActions: isAdmin }), [isAdmin, readiness]);

  const refreshWorkspace = useCallback(async () => {
    setIsRefreshing(true);
    try {
      let compatibilityMode = false;
      const [overviewPayload, readinessPayload, configPayload, libraryPayload] = await Promise.all([
        fetchWechatOfficialOverview(),
        fetchWechatOfficialReadiness().catch(() => {
          compatibilityMode = true;
          return fallbackReadiness;
        }),
        isAdmin ? fetchWechatOfficialRedfoxConfig() : Promise.resolve({ configured: false, config: null }),
        fetchWechatOfficialContentLibrary(),
      ]);
      setOverview(overviewPayload);
      setReadiness(readinessPayload);
      setConfigured(configPayload.configured);
      setRedfoxConfig(configPayload.config);
      setContentItems(libraryPayload.items);
      setReadinessCompatibilityMode(compatibilityMode);
      setLoadFailed(false);
    } catch {
      setOverview(fallbackOverview);
      setReadiness(fallbackReadiness);
      setReadinessCompatibilityMode(true);
      setLoadFailed(true);
    } finally {
      setIsRefreshing(false);
    }
  }, [isAdmin]);

  useEffect(() => {
    void refreshWorkspace();
  }, [refreshWorkspace]);

  return (
    <PlatformSectionPage
      platformLabel="微信公众号"
      title="公众号运营总览"
      description="汇总 Redfox 配置、爆文候选、内容库和 blocked 动作状态。"
      safetyMessage="Redfox 是内容数据源，不是公众号发布通道"
      safetyDescription="爆文发现只收集候选并交给内容库；内容库和草稿工坊各自处理素材、拆解与草稿能力。真实授权、素材上传、草稿同步、预览发送、群发发布没有可执行入口。"
      action={(
        <Space>
          <Tag color="red">发布/群发 blocked</Tag>
          <Button icon={<SyncOutlined />} loading={isRefreshing} onClick={() => void refreshWorkspace()}>刷新</Button>
        </Space>
      )}
    >
      {loadFailed ? (
        <Alert showIcon type="warning" style={{ marginBottom: 16 }} message="公众号数据读取失败" description="已保留本地 fallback 状态。请确认已登录主系统且后端服务可用。" />
      ) : null}

      <Row gutter={[16, 16]}>
        <Col xs={24} md={8} xl={6}><Card style={cardStyle}><Statistic title="Readiness" value={readiness.summary.overall_status} prefix={<SafetyCertificateOutlined />} /></Card></Col>
        <Col xs={24} md={8} xl={6}><Card style={cardStyle}><Statistic title="Redfox" value={configuredText} prefix={<SafetyCertificateOutlined />} /></Card></Col>
        <Col xs={24} md={8} xl={6}><Card style={cardStyle}><Statistic title="爆文候选" value={candidateCount} prefix={<DatabaseOutlined />} /></Card></Col>
        <Col xs={24} md={8} xl={6}><Card style={cardStyle}><Statistic title="内容库" value={libraryCount} prefix={<FileTextOutlined />} /></Card></Col>
        <Col xs={24} md={8} xl={6}><Card style={cardStyle}><Statistic title="公众号草稿" value={readiness.drafts.count} prefix={<FileTextOutlined />} /></Card></Col>
        <Col xs={24} md={8} xl={6}><Card style={cardStyle}><Statistic title="候选图" value={readiness.content.images} prefix={<FileTextOutlined />} /></Card></Col>
        <Col xs={24} md={8} xl={6}><Card style={cardStyle}><Statistic title="Blocked actions" value={overview.blocked_actions.length} prefix={<LockOutlined />} /></Card></Col>
        <Col xs={24}>
          <PlatformReadinessPanel
            overallStatus={readiness.summary.overall_status}
            nextActions={readiness.summary.next_actions}
            checks={readiness.checks}
            actions={readinessActions}
            compatibilityMode={readinessCompatibilityMode}
            blockedTags={["publish blocked", "sendall blocked", "preview blocked", "material upload blocked"]}
          />
        </Col>
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
      </Row>
    </PlatformSectionPage>
  );
}

export const WechatOfficialDashboard = WechatOfficialDashboardPage;
