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
  DatePicker,
  Divider,
  Form,
  Input,
  InputNumber,
  List,
  message,
  Row,
  Segmented,
  Space,
  Statistic,
  Tag,
  Typography,
} from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { PageHeader } from "../../components/layout/app-shell";
import {
  collectWechatOfficialRedfoxAccount,
  collectWechatOfficialRedfoxArticles,
  createWechatOfficialDraft,
  dryRunWechatOfficialDraft,
  fetchWechatOfficialContentLibrary,
  fetchWechatOfficialOverview,
  fetchWechatOfficialRedfoxConfig,
  importWechatOfficialRedfoxUrl,
  saveWechatOfficialRedfoxConfig,
  updateWechatOfficialRecommendation,
  validateWechatOfficialRedfoxConfig,
} from "../../lib/api";
import type {
  WechatOfficialContentLibraryItem,
  WechatOfficialOverview,
  WechatOfficialRedfoxCollectResponse,
  WechatOfficialRedfoxConfig,
} from "../../types";

const { Text, Paragraph } = Typography;
const { RangePicker } = DatePicker;

const cardStyle = { background: "#1f1f1f", borderColor: "#303030" };
const DEFAULT_MIN_READ = 100000;

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

type RedfoxMode = "keyword" | "account" | "url";

type KeywordForm = {
  keyword: string;
  pages: number;
  min_read_count: number;
};

type AccountForm = {
  account: string;
  account_name?: string;
  pages: number;
  min_read_count: number;
  range?: unknown;
};

type UrlForm = {
  url: string;
  min_read_count: number;
};

function statusColor(status?: string): string {
  if (!status) return "default";
  if (["blocked", "expired", "invalid", "failed"].includes(status)) return "red";
  if (["planned", "partial", "pending", "unknown"].includes(status)) return "gold";
  if (["available", "valid", "active", "succeeded", "completed"].includes(status)) return "green";
  return "default";
}

function readCount(article: WechatOfficialContentLibraryItem): number {
  return Number(article.latest_metric?.read_count ?? 0);
}

function lowFollowerLabel(article: WechatOfficialContentLibraryItem): string {
  const value = article.analysis?.low_follower_evidence;
  if (value === "manual") return "人工确认";
  if (value === "inferred") return "Redfox 推断";
  if (value === true) return "已有证据";
  if (value === false) return "无证据";
  return "未知";
}

function collectSummaryText(result: WechatOfficialRedfoxCollectResponse | null): string {
  if (!result) return "尚未执行收集";
  const { summary } = result;
  return `拉取 ${summary.fetched}，保存 ${summary.saved}，10万+候选 ${summary.viral_candidates}，重复 ${summary.deduped}，API 调用 ${summary.api_calls}`;
}

export function WechatOfficialDashboard() {
  const [overview, setOverview] = useState<WechatOfficialOverview>(fallbackOverview);
  const [redfoxConfig, setRedfoxConfig] = useState<WechatOfficialRedfoxConfig | null>(null);
  const [configured, setConfigured] = useState(false);
  const [contentItems, setContentItems] = useState<WechatOfficialContentLibraryItem[]>([]);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [mode, setMode] = useState<RedfoxMode>("keyword");
  const [lastCollectResult, setLastCollectResult] = useState<WechatOfficialRedfoxCollectResponse | null>(null);
  const [draftIdByArticle, setDraftIdByArticle] = useState<Record<number, number>>({});

  const [configForm] = Form.useForm();
  const [keywordForm] = Form.useForm<KeywordForm>();
  const [accountForm] = Form.useForm<AccountForm>();
  const [urlForm] = Form.useForm<UrlForm>();

  const candidateCount = useMemo(() => contentItems.filter((item) => item.is_candidate).length, [contentItems]);
  const configuredText = configured ? `已配置 ${redfoxConfig?.masked_api_key || "****"}` : "未配置";

  const refreshWorkspace = useCallback(async () => {
    try {
      const [overviewPayload, configPayload, libraryPayload] = await Promise.all([
        fetchWechatOfficialOverview(),
        fetchWechatOfficialRedfoxConfig(),
        fetchWechatOfficialContentLibrary({ viral_only: true, min_read_count: DEFAULT_MIN_READ }),
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
      message.error(error instanceof Error ? error.message : "操作失败，请检查输入和后端状态。");
    } finally {
      setBusyAction(null);
    }
  }

  const handleSaveConfig = () => runAction("save-config", "Redfox API Key 配置已保存", async () => {
    const values = await configForm.validateFields();
    const payload = {
      name: values.name,
      base_url: values.base_url,
      api_key: String(values.api_key || "").trim() || undefined,
    };
    const response = await saveWechatOfficialRedfoxConfig(payload);
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

  const handleKeywordCollect = () => runAction("collect-keyword", "关键词爆文收集完成", async () => {
    const values = await keywordForm.validateFields();
    const response = await collectWechatOfficialRedfoxArticles({
      keyword: values.keyword,
      pages: values.pages ?? 1,
      sort_type: "_4",
      min_read_count: values.min_read_count ?? DEFAULT_MIN_READ,
      save_snapshot: true,
    });
    setLastCollectResult(response);
    await refreshWorkspace();
  });

  const handleAccountCollect = () => runAction("collect-account", "公众号爆文收集完成", async () => {
    const values = await accountForm.validateFields();
    const range = Array.isArray(values.range) ? values.range : [];
    const response = await collectWechatOfficialRedfoxAccount({
      account: values.account,
      account_name: values.account_name || "",
      pages: values.pages ?? 1,
      sort_type: "_4",
      publish_time_start: range[0] && typeof range[0] === "object" && "format" in range[0] ? (range[0] as { format: (f: string) => string }).format("YYYY-MM-DD") : undefined,
      publish_time_end: range[1] && typeof range[1] === "object" && "format" in range[1] ? (range[1] as { format: (f: string) => string }).format("YYYY-MM-DD") : undefined,
      min_read_count: values.min_read_count ?? DEFAULT_MIN_READ,
      save_snapshot: true,
    });
    setLastCollectResult(response);
    await refreshWorkspace();
  });

  const handleUrlImport = () => runAction("import-url", "文章 URL 已补全入库", async () => {
    const values = await urlForm.validateFields();
    const response = await importWechatOfficialRedfoxUrl({
      url: values.url,
      min_read_count: values.min_read_count ?? DEFAULT_MIN_READ,
      save_snapshot: true,
    });
    setLastCollectResult(response);
    await refreshWorkspace();
  });

  const handleCreateDraft = (article: WechatOfficialContentLibraryItem) => runAction(`draft-${article.id}`, "已生成公众号二创草稿", async () => {
    const draft = await createWechatOfficialDraft(article.id, {
      rewrite_style: "保留爆文结构，提炼可复用案例价值",
      target_audience: "私域运营和内容负责人",
      call_to_action: "关注后续更新",
    });
    setDraftIdByArticle((current) => ({ ...current, [article.id]: draft.id }));
  });

  const handleDryRun = (article: WechatOfficialContentLibraryItem) => runAction(`dry-${article.id}`, "dry-run 完成：真实发布和群发保持 blocked", async () => {
    let draftId = draftIdByArticle[article.id];
    if (!draftId) {
      const draft = await createWechatOfficialDraft(article.id, {
        rewrite_style: "保留爆文结构，提炼可复用案例价值",
        target_audience: "私域运营和内容负责人",
        call_to_action: "关注后续更新",
      });
      draftId = draft.id;
      setDraftIdByArticle((current) => ({ ...current, [article.id]: draft.id }));
    }
    const result = await dryRunWechatOfficialDraft(draftId, {});
    if (!result.publish_blocked || !result.sendall_blocked) {
      throw new Error("dry-run 未返回 blocked 状态，请检查后端安全契约。");
    }
  });

  const handleMarkRecommended = (article: WechatOfficialContentLibraryItem) => runAction(`recommend-${article.id}`, "已标记为 recommended", async () => {
    await updateWechatOfficialRecommendation(article.id, { recommendation_status: "recommended" });
    await refreshWorkspace();
  });

  const handleMarkManualLowFollower = (article: WechatOfficialContentLibraryItem) => runAction(`low-${article.id}`, "已标记低粉证据为人工确认", async () => {
    await updateWechatOfficialRecommendation(article.id, { low_follower_evidence: "manual", low_follower_note: "人工确认低粉爆文证据" });
    await refreshWorkspace();
  });

  return (
    <div>
      <PageHeader
        eyebrow="运营中台 / 微信公众号"
        title="Redfox 公众号爆文收集"
        description="通过 RedFoxHub 官方 API 收集公众号 10万+ 文章，沉淀为爆文候选并生成二创草稿。真实发布与群发保持阻断。"
        action={
          <Space>
            <Tag color="red">发布/群发 blocked</Tag>
            <Button icon={<SyncOutlined />} loading={busyAction === "refresh"} onClick={() => runAction("refresh", "页面已刷新", refreshWorkspace)}>刷新</Button>
            <Link to="/platform-select"><Button icon={<ArrowLeftOutlined />}>平台中心</Button></Link>
          </Space>
        }
      />

      {loadFailed ? (
        <Alert showIcon type="warning" style={{ marginBottom: 16 }} message="公众号数据读取失败" description="已保留本地 fallback 状态。请确认已登录主系统且后端服务可用。" />
      ) : null}

      <Alert
        showIcon
        type="info"
        style={{ marginBottom: 16 }}
        message="Redfox 是内容数据源，不是公众号发布通道"
        description="本页面只做爆文收集、候选入库、草稿生成和 dry-run。真实授权、素材上传、草稿同步、预览发送、群发发布没有可执行入口。"
      />

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} md={8} xl={6}><Card style={cardStyle}><Statistic title="Redfox" value={configuredText} prefix={<SafetyCertificateOutlined />} /></Card></Col>
        <Col xs={24} md={8} xl={6}><Card style={cardStyle}><Statistic title="10万+ 候选" value={candidateCount} prefix={<DatabaseOutlined />} /></Card></Col>
        <Col xs={24} md={8} xl={6}><Card style={cardStyle}><Statistic title="内容库展示" value={contentItems.length} prefix={<FileTextOutlined />} /></Card></Col>
        <Col xs={24} md={8} xl={6}><Card style={cardStyle}><Statistic title="Blocked actions" value={overview.blocked_actions.length} prefix={<LockOutlined />} /></Card></Col>
      </Row>

      <Row gutter={[16, 16]}>
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

        <Col xs={24} xl={16}>
          <Card title="爆文收集" style={cardStyle}>
            <Segmented
              value={mode}
              onChange={(value) => setMode(value as RedfoxMode)}
              options={[{ label: "按关键词收集", value: "keyword" }, { label: "按公众号收集", value: "account" }, { label: "文章 URL 补全", value: "url" }]}
              style={{ marginBottom: 16 }}
            />

            {mode === "keyword" ? (
              <Form form={keywordForm} layout="inline" initialValues={{ pages: 1, min_read_count: DEFAULT_MIN_READ }}>
                <Form.Item name="keyword" rules={[{ required: true, message: "请输入关键词" }]}><Input placeholder="关键词，如 私域增长" /></Form.Item>
                <Form.Item name="pages" label="页数"><InputNumber min={1} max={3} /></Form.Item>
                <Form.Item name="min_read_count" label="最低阅读"><InputNumber min={0} step={10000} /></Form.Item>
                <Form.Item><Button type="primary" loading={busyAction === "collect-keyword"} onClick={handleKeywordCollect}>开始收集爆文</Button></Form.Item>
              </Form>
            ) : null}

            {mode === "account" ? (
              <Form form={accountForm} layout="vertical" initialValues={{ pages: 1, min_read_count: DEFAULT_MIN_READ }}>
                <Row gutter={12}>
                  <Col xs={24} md={8}><Form.Item name="account" label="公众号微信号" rules={[{ required: true, message: "请输入公众号微信号" }]}><Input placeholder="rmrbwx" /></Form.Item></Col>
                  <Col xs={24} md={8}><Form.Item name="account_name" label="公众号名称"><Input placeholder="人民日报" /></Form.Item></Col>
                  <Col xs={24} md={8}><Form.Item name="range" label="时间范围"><RangePicker style={{ width: "100%" }} /></Form.Item></Col>
                  <Col xs={12} md={6}><Form.Item name="pages" label="页数"><InputNumber min={1} max={3} style={{ width: "100%" }} /></Form.Item></Col>
                  <Col xs={12} md={6}><Form.Item name="min_read_count" label="最低阅读"><InputNumber min={0} step={10000} style={{ width: "100%" }} /></Form.Item></Col>
                  <Col xs={24} md={8}><Form.Item label=" "><Button type="primary" loading={busyAction === "collect-account"} onClick={handleAccountCollect}>收集该公众号爆文</Button></Form.Item></Col>
                </Row>
              </Form>
            ) : null}

            {mode === "url" ? (
              <Form form={urlForm} layout="inline" initialValues={{ min_read_count: DEFAULT_MIN_READ }}>
                <Form.Item name="url" rules={[{ required: true, message: "请输入文章 URL" }]} style={{ minWidth: 360 }}><Input placeholder="https://mp.weixin.qq.com/s/..." /></Form.Item>
                <Form.Item name="min_read_count" label="最低阅读"><InputNumber min={0} step={10000} /></Form.Item>
                <Form.Item><Button type="primary" loading={busyAction === "import-url"} onClick={handleUrlImport}>查询并入库</Button></Form.Item>
              </Form>
            ) : null}

            <Divider />
            <Alert showIcon type="success" message="最近一次收集结果" description={collectSummaryText(lastCollectResult)} />
            <Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>默认 1 页，最多 3 页；Redfox 是付费 API，执行前请关注预计 API 调用次数。</Paragraph>
          </Card>
        </Col>

        <Col xs={24}>
          <Card title="10万+ 爆文候选库" style={cardStyle}>
            <List
              dataSource={contentItems}
              locale={{ emptyText: "暂无 10万+ 候选文章；先配置 Redfox 并执行收集。" }}
              renderItem={(article) => (
                <List.Item
                  actions={[
                    <Button key="draft" size="small" loading={busyAction === `draft-${article.id}`} onClick={() => handleCreateDraft(article)}>生成二创草稿</Button>,
                    <Button key="dry" size="small" loading={busyAction === `dry-${article.id}`} onClick={() => handleDryRun(article)}>Dry-run</Button>,
                    <Button key="rec" size="small" loading={busyAction === `recommend-${article.id}`} onClick={() => handleMarkRecommended(article)}>标记推荐</Button>,
                    <Button key="low" size="small" loading={busyAction === `low-${article.id}`} onClick={() => handleMarkManualLowFollower(article)}>标记低粉证据</Button>,
                  ]}
                >
                  <List.Item.Meta
                    title={
                      <Space wrap>
                        <Text strong>{article.title || `Article #${article.id}`}</Text>
                        <Tag color="green">Redfox</Tag>
                        <Tag color={article.is_candidate ? "red" : "default"}>{article.is_candidate ? "爆文候选" : "普通文章"}</Tag>
                        <Tag color="blue">阅读 {readCount(article).toLocaleString()}</Tag>
                        <Tag color={statusColor(String(article.analysis?.recommendation_status || "candidate"))}>{String(article.analysis?.recommendation_status || "candidate")}</Tag>
                        <Tag>{lowFollowerLabel(article)}</Tag>
                      </Space>
                    }
                    description={
                      <Space direction="vertical" size={4}>
                        <Text type="secondary">公众号/作者：{article.author_name || "未知"} · 发布时间：{article.publish_time_remote || "未知"}</Text>
                        <Text type="secondary">点赞 {article.latest_metric?.like_count ?? 0} / 在看 {article.latest_metric?.wow_count ?? 0} / 评论 {article.latest_metric?.comment_count ?? 0} / 分享 {article.latest_metric?.share_count ?? 0}</Text>
                        <Text>{article.digest || article.article_url}</Text>
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          </Card>
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
    </div>
  );
}
