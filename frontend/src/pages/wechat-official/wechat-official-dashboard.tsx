import {
  ApiOutlined,
  ArrowLeftOutlined,
  CheckCircleOutlined,
  CloudSyncOutlined,
  DatabaseOutlined,
  LockOutlined,
  SafetyCertificateOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Input,
  InputNumber,
  List,
  message,
  Row,
  Select,
  Space,
  Statistic,
  Tag,
  Typography,
} from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { PageHeader } from "../../components/layout/app-shell";
import {
  captureWechatOfficialArticleComments,
  captureWechatOfficialArticleMetrics,
  captureWechatOfficialArticleSnapshot,
  completeWechatOfficialQrLogin,
  createWechatOfficialDraft,
  dryRunWechatOfficialDraft,
  fetchWechatOfficialContentLibrary,
  fetchWechatOfficialCredentialGuide,
  fetchWechatOfficialCredentials,
  fetchWechatOfficialOverview,
  fetchWechatOfficialProxies,
  fetchWechatOfficialSessions,
  importWechatOfficialCredential,
  searchWechatOfficialAccounts,
  startWechatOfficialQrLogin,
  syncWechatOfficialArticles,
  testWechatOfficialProxy,
  updateWechatOfficialRecommendation,
  validateWechatOfficialCredential,
} from "../../lib/api";
import type {
  WechatOfficialArticle,
  WechatOfficialBackendSession,
  WechatOfficialContentLibraryItem,
  WechatOfficialCrawlAccount,
  WechatOfficialCredential,
  WechatOfficialCredentialGuide,
  WechatOfficialOverview,
  WechatOfficialProxy,
} from "../../types";

const { Text, Title, Paragraph } = Typography;
const { TextArea } = Input;

const cardStyle = { background: "#1f1f1f", borderColor: "#303030" };

const fallbackOverview: WechatOfficialOverview = {
  platform_id: "wechat_official",
  stage: "foundation_ready",
  external_integration_enabled: false,
  research_required_before_integration: true,
  research_topics: [
    "GitHub 微信公众号开源系统架构调研",
    "微信官方草稿箱、素材、群发、预览 API 能力边界确认",
    "凭据保存与加密策略确认",
    "真实群发风险与 QA 流程确认",
  ],
  capabilities: [
    {
      key: "crawl.backend",
      label: "后台采集",
      status: "partial",
      message: "本阶段支持模拟后台 session、手动 upstream JSON 导入和内容库沉淀。",
    },
    {
      key: "publish.real_publish",
      label: "群发发布",
      status: "blocked",
      message: "高风险动作，正式 QA、dry-run 和动作级确认机制完成前保持阻断。",
    },
  ],
  blocked_actions: ["真实授权", "素材上传", "草稿同步", "预览发送", "群发发布"],
};

const fallbackGuide: WechatOfficialCredentialGuide = {
  title: "微信公众号文章 credential.py 导入引导",
  expected_fields: ["biz", "uin", "key", "pass_ticket", "wap_sid2", "appmsg_token", "cookie", "timestamp"],
  steps: [],
  risk_warnings: ["credential 只保存在服务端加密存储；前端不写入 localStorage。"],
};

function statusColor(status: string): string {
  if (status === "blocked" || status === "expired" || status === "invalid" || status === "cooldown") return "red";
  if (status === "planned" || status === "partial" || status === "pending") return "gold";
  if (status === "available" || status === "valid" || status === "active" || status === "succeeded") return "green";
  return "default";
}

function parseJsonObject(value: string, label: string): Record<string, unknown> {
  const trimmed = value.trim();
  if (!trimmed) return {};
  const parsed = JSON.parse(trimmed) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`${label} 必须是 JSON object`);
  }
  return parsed as Record<string, unknown>;
}

function readCount(article: WechatOfficialContentLibraryItem): number {
  return Number(article.latest_metric?.read_count ?? 0);
}

function articleSummary(article: WechatOfficialArticle): string {
  return article.digest || article.article_url || "暂无摘要";
}

export function WechatOfficialDashboard() {
  const [overview, setOverview] = useState<WechatOfficialOverview>(fallbackOverview);
  const [guide, setGuide] = useState<WechatOfficialCredentialGuide>(fallbackGuide);
  const [sessions, setSessions] = useState<WechatOfficialBackendSession[]>([]);
  const [credentials, setCredentials] = useState<WechatOfficialCredential[]>([]);
  const [proxies, setProxies] = useState<WechatOfficialProxy[]>([]);
  const [accounts, setAccounts] = useState<WechatOfficialCrawlAccount[]>([]);
  const [contentItems, setContentItems] = useState<WechatOfficialContentLibraryItem[]>([]);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);

  const [loginSessionId, setLoginSessionId] = useState<number | null>(null);
  const [loginCompleteJson, setLoginCompleteJson] = useState(
    JSON.stringify({ cookie: "dev-cookie", token: "dev-token", auth_key: "dev-auth-key", biz: "", nickname: "开发模拟账号" }, null, 2)
  );
  const [credentialJson, setCredentialJson] = useState("");
  const [searchBackendSessionId, setSearchBackendSessionId] = useState<number | null>(null);
  const [searchKeyword, setSearchKeyword] = useState("");
  const [searchUpstreamJson, setSearchUpstreamJson] = useState("");
  const [syncBackendSessionId, setSyncBackendSessionId] = useState<number | null>(null);
  const [syncAccountId, setSyncAccountId] = useState<number | null>(null);
  const [syncKeyword, setSyncKeyword] = useState("");
  const [syncLimit, setSyncLimit] = useState(20);
  const [syncUpstreamJson, setSyncUpstreamJson] = useState("");
  const [selectedArticleId, setSelectedArticleId] = useState<number | null>(null);
  const [snapshotHtml, setSnapshotHtml] = useState("");
  const [metricCredentialId, setMetricCredentialId] = useState<number | null>(null);
  const [metricHtml, setMetricHtml] = useState("");
  const [metricCgiJson, setMetricCgiJson] = useState("");
  const [commentsJson, setCommentsJson] = useState("");
  const [draftId, setDraftId] = useState<number | null>(null);

  const activeSessions = useMemo(() => sessions.filter((item) => item.status === "valid" || item.status === "active"), [sessions]);
  const selectedArticle = useMemo(
    () => contentItems.find((item) => item.id === selectedArticleId) ?? null,
    [contentItems, selectedArticleId]
  );

  const refreshWorkbench = useCallback(async () => {
    try {
      const [overviewPayload, guidePayload, sessionsPayload, credentialsPayload, proxiesPayload, libraryPayload] = await Promise.all([
        fetchWechatOfficialOverview(),
        fetchWechatOfficialCredentialGuide(),
        fetchWechatOfficialSessions(),
        fetchWechatOfficialCredentials(),
        fetchWechatOfficialProxies(),
        fetchWechatOfficialContentLibrary(),
      ]);
      setOverview(overviewPayload);
      setGuide(guidePayload);
      setSessions(sessionsPayload.items);
      setCredentials(credentialsPayload.items);
      setProxies(proxiesPayload.items);
      setContentItems(libraryPayload.items);
      setLoadFailed(false);
    } catch {
      setOverview(fallbackOverview);
      setGuide(fallbackGuide);
      setLoadFailed(true);
    }
  }, []);

  useEffect(() => {
    void refreshWorkbench();
  }, [refreshWorkbench]);

  async function runAction(actionKey: string, successText: string, action: () => Promise<void>): Promise<void> {
    setBusyAction(actionKey);
    try {
      await action();
      message.success(successText);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "操作失败，请检查输入和后端状态。");
    } finally {
      setBusyAction(null);
    }
  }

  const handleStartLogin = () => runAction("start-login", "已创建模拟二维码登录会话", async () => {
    const payload = await startWechatOfficialQrLogin();
    setLoginSessionId(payload.login_session_id);
    await refreshWorkbench();
  });

  const handleCompleteLogin = () => runAction("complete-login", "已模拟完成后台登录", async () => {
    if (!loginSessionId) throw new Error("请先 start qrcode 或填写 login_session_id。");
    const payload = parseJsonObject(loginCompleteJson, "模拟完成登录 payload");
    await completeWechatOfficialQrLogin(loginSessionId, {
      cookie: String(payload.cookie ?? ""),
      token: String(payload.token ?? ""),
      auth_key: String(payload.auth_key ?? ""),
      biz: typeof payload.biz === "string" ? payload.biz : undefined,
      nickname: typeof payload.nickname === "string" ? payload.nickname : undefined,
      user_agent: typeof payload.user_agent === "string" ? payload.user_agent : undefined,
      expires_at: typeof payload.expires_at === "string" ? payload.expires_at : undefined,
    });
    setLoginCompleteJson("");
    await refreshWorkbench();
  });

  const handleImportCredential = () => runAction("credential-import", "credential 已导入服务端", async () => {
    const payload = parseJsonObject(credentialJson, "credential JSON");
    const validation = await validateWechatOfficialCredential(payload);
    if (!validation.valid) {
      throw new Error(`credential 缺少字段：${validation.missing_fields.join(", ")}`);
    }
    await importWechatOfficialCredential({
      biz: String(payload.biz ?? ""),
      uin: String(payload.uin ?? ""),
      key: String(payload.key ?? ""),
      pass_ticket: String(payload.pass_ticket ?? ""),
      wap_sid2: String(payload.wap_sid2 ?? ""),
      appmsg_token: String(payload.appmsg_token ?? ""),
      cookie: String(payload.cookie ?? ""),
      timestamp: typeof payload.timestamp === "number" ? payload.timestamp : String(payload.timestamp ?? ""),
      nickname: typeof payload.nickname === "string" ? payload.nickname : undefined,
      article_url: typeof payload.article_url === "string" ? payload.article_url : undefined,
      captured_at: typeof payload.captured_at === "string" ? payload.captured_at : undefined,
    });
    setCredentialJson("");
    await refreshWorkbench();
  });

  const handleProxyTest = (proxy: WechatOfficialProxy, success: boolean) => runAction(
    `proxy-${proxy.id}-${success}`,
    success ? "代理测试成功" : "代理测试失败已记录",
    async () => {
      await testWechatOfficialProxy(proxy.id, {
        request_type: "public",
        success,
        error_message: success ? "" : "manual frontend test failed",
      });
      await refreshWorkbench();
    }
  );

  const handleSearchAccounts = () => runAction("search-accounts", "公众号候选账号已导入", async () => {
    if (!searchBackendSessionId) throw new Error("请输入 backend_session_id。");
    if (!searchKeyword.trim()) throw new Error("请输入 keyword。");
    const payload = parseJsonObject(searchUpstreamJson, "searchbiz upstream JSON");
    const response = await searchWechatOfficialAccounts({
      backend_session_id: searchBackendSessionId,
      keyword: searchKeyword.trim(),
      upstream_payload: payload,
    });
    setAccounts(response.items);
  });

  const handleSyncArticles = () => runAction("sync-articles", "文章已同步到内容库", async () => {
    if (!syncBackendSessionId) throw new Error("请输入 backend_session_id。");
    const payload = parseJsonObject(syncUpstreamJson, "appmsgpublish upstream JSON");
    const response = await syncWechatOfficialArticles({
      backend_session_id: syncBackendSessionId,
      account_id: syncAccountId,
      keyword: syncKeyword.trim(),
      limit: syncLimit,
      upstream_payload: payload,
    });
    setContentItems(response.items);
    setSelectedArticleId(response.items[0]?.id ?? selectedArticleId);
    await refreshWorkbench();
  });

  const handleMarkRecommendation = (article: WechatOfficialContentLibraryItem, recommended: boolean) => runAction(
    `recommend-${article.id}-${recommended}`,
    recommended ? "已标记 recommended" : "已标记 manual low follower evidence",
    async () => {
      await updateWechatOfficialRecommendation(article.id, recommended
        ? { recommendation_status: "recommended" }
        : { low_follower_evidence: true, low_follower_note: "manual frontend evidence" });
      await refreshWorkbench();
    }
  );

  const handleSnapshot = () => runAction("snapshot", "HTML snapshot 已保存", async () => {
    if (!selectedArticleId) throw new Error("请先选择 article_id。");
    await captureWechatOfficialArticleSnapshot(selectedArticleId, { html: snapshotHtml });
    setSnapshotHtml("");
  });

  const handleMetrics = () => runAction("metrics", "指标已保存", async () => {
    if (!selectedArticleId) throw new Error("请先选择 article_id。");
    if (!metricCredentialId) throw new Error("请输入 credential_id。");
    await captureWechatOfficialArticleMetrics(selectedArticleId, {
      credential_id: metricCredentialId,
      html: metricHtml || null,
      cgi_data: parseJsonObject(metricCgiJson, "cgi_data JSON"),
    });
    setMetricHtml("");
    setMetricCgiJson("");
    await refreshWorkbench();
  });

  const handleComments = () => runAction("comments", "评论 payload 已保存", async () => {
    if (!selectedArticleId) throw new Error("请先选择 article_id。");
    await captureWechatOfficialArticleComments(selectedArticleId, {
      comments_payload: parseJsonObject(commentsJson, "comments payload JSON"),
      limit: 50,
    });
    setCommentsJson("");
  });

  const handleCreateDraft = () => runAction("create-draft", "已创建公众号草稿（本地 dry-run 用）", async () => {
    if (!selectedArticleId) throw new Error("请先选择 article_id。");
    const draft = await createWechatOfficialDraft(selectedArticleId, {
      rewrite_style: "保持原文结构，提炼案例价值",
      target_audience: "私域运营和内容负责人",
      call_to_action: "关注后续更新",
    });
    setDraftId(draft.id);
  });

  const handleDryRun = () => runAction("dry-run", "dry-run 完成：真实发布和群发保持 blocked", async () => {
    if (!draftId) throw new Error("请先创建草稿或填写 draft_id。");
    const result = await dryRunWechatOfficialDraft(draftId, {});
    if (!result.publish_blocked || !result.sendall_blocked) {
      throw new Error("dry-run 未返回 blocked 状态，请检查后端契约。");
    }
  });

  return (
    <div>
      <PageHeader
        eyebrow="WeChat Official Crawl Workbench"
        title="微信公众号采集工作台"
        description="用于灰度验证后台 session、credential、代理、候选文章、指标评论与本地草稿 dry-run；真实授权、素材上传、预览和群发继续阻断。"
        action={
          <Space>
            <Button icon={<SyncOutlined />} loading={busyAction === "refresh"} onClick={() => runAction("refresh", "工作台已刷新", refreshWorkbench)}>
              刷新
            </Button>
            <Link to="/platform-select">
              <Button icon={<ArrowLeftOutlined />}>返回平台中心</Button>
            </Link>
          </Space>
        }
      />

      {loadFailed ? (
        <Alert
          showIcon
          type="warning"
          style={{ marginBottom: 16 }}
          message="公众号工作台部分数据读取失败"
          description="当前保留本地 fallback 状态。请确认已登录主系统且后端服务可用；credential secret 不会写入浏览器持久化存储。"
        />
      ) : null}

      <Alert
        showIcon
        type="error"
        style={{ marginBottom: 16 }}
        message="真实发布链路保持 blocked"
        description="本页面只提供采集、导入、内容库标记、草稿创建和 dry-run。真实授权、素材上传、草稿同步、预览发送、群发发布没有可执行按钮。"
      />

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} md={8} xl={4}>
          <Card style={cardStyle}><Statistic title="阶段" value="Beta" prefix={<CheckCircleOutlined />} /></Card>
        </Col>
        <Col xs={24} md={8} xl={5}>
          <Card style={cardStyle}><Statistic title="采集账号 / session" value={`${accounts.length} / ${sessions.length}`} prefix={<ApiOutlined />} /></Card>
        </Col>
        <Col xs={24} md={8} xl={5}>
          <Card style={cardStyle}><Statistic title="Credential" value={credentials.length} prefix={<SafetyCertificateOutlined />} /></Card>
        </Col>
        <Col xs={24} md={8} xl={4}>
          <Card style={cardStyle}><Statistic title="Proxy" value={proxies.length} prefix={<CloudSyncOutlined />} /></Card>
        </Col>
        <Col xs={24} md={8} xl={4}>
          <Card style={cardStyle}><Statistic title="候选文章" value={contentItems.length} prefix={<DatabaseOutlined />} /></Card>
        </Col>
        <Col xs={24} md={8} xl={2}>
          <Card style={cardStyle}><Statistic title="Blocked" value={overview.blocked_actions.length} prefix={<LockOutlined />} /></Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card title="后台登录 session（开发模拟）" style={cardStyle}>
            <Alert
              showIcon
              type="info"
              style={{ marginBottom: 12 }}
              message="模拟完成登录不是微信真实登录"
              description="后端当前 complete 接口接收开发 payload 并加密保存 cookie/token/auth_key；前端只把输入放在组件 state，用完会清空。"
            />
            <Space wrap style={{ marginBottom: 12 }}>
              <Button type="primary" loading={busyAction === "start-login"} onClick={handleStartLogin}>Start QRCode</Button>
              <InputNumber min={1} placeholder="login_session_id" value={loginSessionId} onChange={(value) => setLoginSessionId(value ?? null)} />
              <Button loading={busyAction === "complete-login"} onClick={handleCompleteLogin}>模拟完成登录</Button>
            </Space>
            <TextArea rows={5} value={loginCompleteJson} onChange={(event) => setLoginCompleteJson(event.target.value)} placeholder="模拟 complete JSON：cookie/token/auth_key/biz/nickname" />
            <Divider />
            <List
              size="small"
              dataSource={sessions}
              locale={{ emptyText: "暂无 session" }}
              renderItem={(item) => (
                <List.Item>
                  <Space wrap>
                    <Text strong>#{item.id}</Text>
                    <Tag color={statusColor(item.status)}>{item.status}</Tag>
                    <Text>account_id={item.account_id}</Text>
                    <Text type="secondary">{item.nickname || item.biz || "未命名"}</Text>
                    {item.expires_at ? <Text type="secondary">expires {item.expires_at}</Text> : null}
                  </Space>
                </List.Item>
              )}
            />
          </Card>
        </Col>

        <Col xs={24} xl={12}>
          <Card title="Credential 引导与导入" style={cardStyle}>
            <Title level={5} style={{ marginTop: 0 }}>{guide.title}</Title>
            <Space wrap style={{ marginBottom: 12 }}>
              {guide.expected_fields.map((field) => <Tag key={field} color="blue">{field}</Tag>)}
            </Space>
            <Alert
              showIcon
              type="warning"
              style={{ marginBottom: 12 }}
              message="风险提示"
              description={guide.risk_warnings.join("；")}
            />
            <TextArea rows={7} value={credentialJson} onChange={(event) => setCredentialJson(event.target.value)} placeholder="粘贴 credential JSON；不会写入 localStorage，导入成功后清空" />
            <Space wrap style={{ marginTop: 12 }}>
              <Button type="primary" loading={busyAction === "credential-import"} onClick={handleImportCredential}>校验并导入 credential</Button>
              <Text type="secondary">valid credentials: {credentials.filter((item) => item.valid).length}</Text>
            </Space>
            <List
              size="small"
              style={{ marginTop: 12 }}
              dataSource={credentials}
              locale={{ emptyText: "暂无 credential" }}
              renderItem={(item) => (
                <List.Item>
                  <Space wrap>
                    <Text strong>#{item.id}</Text>
                    <Tag color={statusColor(item.status)}>{item.status}</Tag>
                    <Text>account_id={item.account_id}</Text>
                    <Text type="secondary">{item.nickname || item.biz}</Text>
                    <Text type="secondary">{item.capabilities.join(", ")}</Text>
                  </Space>
                </List.Item>
              )}
            />
          </Card>
        </Col>

        <Col xs={24} xl={10}>
          <Card title="代理池" style={cardStyle}>
            <List
              dataSource={proxies}
              locale={{ emptyText: "暂无代理" }}
              renderItem={(proxy) => (
                <List.Item
                  actions={[
                    <Button key="ok" size="small" loading={busyAction === `proxy-${proxy.id}-true`} onClick={() => handleProxyTest(proxy, true)}>成功</Button>,
                    <Button key="fail" size="small" danger loading={busyAction === `proxy-${proxy.id}-false`} onClick={() => handleProxyTest(proxy, false)}>失败</Button>,
                  ]}
                >
                  <List.Item.Meta
                    title={<Space wrap><Text strong>{proxy.name}</Text><Tag>{proxy.type}</Tag><Tag color={statusColor(proxy.status)}>{proxy.status}</Tag></Space>}
                    description={<Space direction="vertical" size={2}><Text type="secondary">{proxy.endpoint}</Text><Text type="secondary">success {proxy.success_count} / failure {proxy.failure_count}{proxy.last_error ? ` / ${proxy.last_error}` : ""}</Text></Space>}
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>

        <Col xs={24} xl={14}>
          <Card title="采集：公众号搜索与文章同步" style={cardStyle}>
            <Row gutter={[12, 12]}>
              <Col xs={24} lg={12}>
                <Title level={5} style={{ marginTop: 0 }}>搜索公众号</Title>
                <Space direction="vertical" style={{ width: "100%" }}>
                  <InputNumber style={{ width: "100%" }} min={1} placeholder="backend_session_id" value={searchBackendSessionId} onChange={(value) => setSearchBackendSessionId(value ?? null)} />
                  <Input placeholder="keyword" value={searchKeyword} onChange={(event) => setSearchKeyword(event.target.value)} />
                  <TextArea rows={6} value={searchUpstreamJson} onChange={(event) => setSearchUpstreamJson(event.target.value)} placeholder="searchbiz upstream JSON" />
                  <Button type="primary" loading={busyAction === "search-accounts"} onClick={handleSearchAccounts}>搜索并导入公众号</Button>
                </Space>
                <List
                  size="small"
                  style={{ marginTop: 12 }}
                  dataSource={accounts}
                  locale={{ emptyText: "暂无搜索结果" }}
                  renderItem={(item) => (
                    <List.Item>
                      <Space wrap>
                        <Text strong>#{item.id}</Text>
                        <Text>{item.name || item.alias || item.fake_id}</Text>
                        <Button size="small" onClick={() => setSyncAccountId(item.id)}>用于同步</Button>
                      </Space>
                    </List.Item>
                  )}
                />
              </Col>
              <Col xs={24} lg={12}>
                <Title level={5} style={{ marginTop: 0 }}>同步文章</Title>
                <Space direction="vertical" style={{ width: "100%" }}>
                  <InputNumber style={{ width: "100%" }} min={1} placeholder="backend_session_id" value={syncBackendSessionId} onChange={(value) => setSyncBackendSessionId(value ?? null)} />
                  <InputNumber style={{ width: "100%" }} min={1} placeholder="account_id（可选）" value={syncAccountId} onChange={(value) => setSyncAccountId(value ?? null)} />
                  <Input placeholder="keyword（可选）" value={syncKeyword} onChange={(event) => setSyncKeyword(event.target.value)} />
                  <InputNumber style={{ width: "100%" }} min={0} max={100} value={syncLimit} onChange={(value) => setSyncLimit(value ?? 20)} />
                  <TextArea rows={6} value={syncUpstreamJson} onChange={(event) => setSyncUpstreamJson(event.target.value)} placeholder="appmsgpublish upstream JSON" />
                  <Button type="primary" loading={busyAction === "sync-articles"} onClick={handleSyncArticles}>同步文章到内容库</Button>
                </Space>
                <Paragraph type="secondary" style={{ marginTop: 12 }}>
                  可用 valid session：{activeSessions.map((item) => `#${item.id}`).join(", ") || "无"}
                </Paragraph>
              </Col>
            </Row>
          </Card>
        </Col>

        <Col xs={24} xl={14}>
          <Card title="内容库候选文章" style={cardStyle}>
            <List
              dataSource={contentItems}
              locale={{ emptyText: "暂无候选文章" }}
              renderItem={(article) => (
                <List.Item
                  actions={[
                    <Button key="select" size="small" type={selectedArticleId === article.id ? "primary" : "default"} onClick={() => setSelectedArticleId(article.id)}>选择</Button>,
                    <Button key="low" size="small" loading={busyAction === `recommend-${article.id}-false`} onClick={() => handleMarkRecommendation(article, false)}>低粉证据</Button>,
                    <Button key="rec" size="small" loading={busyAction === `recommend-${article.id}-true`} onClick={() => handleMarkRecommendation(article, true)}>推荐</Button>,
                  ]}
                >
                  <List.Item.Meta
                    title={
                      <Space wrap>
                        <Text strong>{article.title || `Article #${article.id}`}</Text>
                        <Tag color={article.is_candidate ? "red" : "default"}>viral_candidate: {String(article.is_candidate)}</Tag>
                        <Tag color={article.analysis?.low_follower_evidence ? "green" : "default"}>low_follower: {String(Boolean(article.analysis?.low_follower_evidence))}</Tag>
                        <Tag color={statusColor(String(article.analysis?.recommendation_status || "new"))}>{String(article.analysis?.recommendation_status || "new")}</Tag>
                      </Space>
                    }
                    description={
                      <Space direction="vertical" size={2}>
                        <Text type="secondary">read_count={readCount(article)} / article_id={article.id} / account_id={article.account_id ?? "-"}</Text>
                        <Text>{articleSummary(article)}</Text>
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>

        <Col xs={24} xl={10}>
          <Card title="评论 / 指标 / Draft dry-run" style={cardStyle}>
            <Space direction="vertical" style={{ width: "100%" }}>
              <Select
                style={{ width: "100%" }}
                placeholder="选择 article_id"
                value={selectedArticleId ?? undefined}
                onChange={(value) => setSelectedArticleId(value)}
                options={contentItems.map((item) => ({ value: item.id, label: `#${item.id} ${item.title || item.article_url}` }))}
              />
              {selectedArticle ? <Alert showIcon type="info" message={`当前文章：${selectedArticle.title || selectedArticle.id}`} /> : null}
              <TextArea rows={4} value={snapshotHtml} onChange={(event) => setSnapshotHtml(event.target.value)} placeholder="HTML snapshot payload" />
              <Button loading={busyAction === "snapshot"} onClick={handleSnapshot}>保存 HTML snapshot</Button>
              <Divider style={{ margin: "8px 0" }} />
              <InputNumber style={{ width: "100%" }} min={1} placeholder="credential_id" value={metricCredentialId} onChange={(value) => setMetricCredentialId(value ?? null)} />
              <TextArea rows={3} value={metricHtml} onChange={(event) => setMetricHtml(event.target.value)} placeholder="metrics HTML（可选）" />
              <TextArea rows={3} value={metricCgiJson} onChange={(event) => setMetricCgiJson(event.target.value)} placeholder="cgi_data JSON（可为空对象）" />
              <Button loading={busyAction === "metrics"} onClick={handleMetrics}>保存指标</Button>
              <Divider style={{ margin: "8px 0" }} />
              <TextArea rows={4} value={commentsJson} onChange={(event) => setCommentsJson(event.target.value)} placeholder="comments payload JSON" />
              <Button loading={busyAction === "comments"} onClick={handleComments}>保存评论</Button>
              <Divider style={{ margin: "8px 0" }} />
              <Space wrap>
                <Button type="primary" loading={busyAction === "create-draft"} onClick={handleCreateDraft}>创建草稿</Button>
                <InputNumber min={1} placeholder="draft_id" value={draftId} onChange={(value) => setDraftId(value ?? null)} />
                <Button loading={busyAction === "dry-run"} onClick={handleDryRun}>Dry-run</Button>
              </Space>
              <Alert showIcon type="error" message="真实发布 / 群发：blocked" description="dry-run 只验证标题、正文和风险检查，不会调用素材上传、预览发送或群发接口。" />
            </Space>
          </Card>
        </Col>

        <Col xs={24}>
          <Card title="Blocked actions" style={cardStyle}>
            <Space wrap>
              {overview.blocked_actions.map((action) => <Tag key={action} color="red">{action}</Tag>)}
              {overview.capabilities.map((capability) => (
                <Tag key={capability.key} color={statusColor(capability.status)}>{capability.label}: {capability.status}</Tag>
              ))}
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
