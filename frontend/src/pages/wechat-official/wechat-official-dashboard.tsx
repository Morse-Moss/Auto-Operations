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
  Descriptions,
  Divider,
  Drawer,
  Form,
  Input,
  Image,
  InputNumber,
  List,
  message,
  Row,
  Segmented,
  Select,
  Space,
  Statistic,
  Tag,
  Typography,
} from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { PageHeader } from "../../components/layout/app-shell";
import {
  analyzeWechatOfficialHotspots,
  collectWechatOfficialRedfoxAccount,
  collectWechatOfficialRedfoxArticles,
  createWechatOfficialDraft,
  dryRunWechatOfficialDraft,
  fetchWechatOfficialContentDetail,
  fetchWechatOfficialContentLibrary,
  fetchWechatOfficialOverview,
  fetchWechatOfficialRedfoxConfig,
  importWechatOfficialRedfoxUrl,
  refreshWechatOfficialContentDetail,
  saveWechatOfficialRedfoxConfig,
  updateWechatOfficialRecommendation,
  validateWechatOfficialRedfoxConfig,
} from "../../lib/api";
import type {
  WechatOfficialContentDetail,
  WechatOfficialContentLibraryItem,
  WechatOfficialCreateDraftPayload,
  WechatOfficialOverview,
  WechatOfficialPoolStatus,
  WechatOfficialRedfoxCollectResponse,
  WechatOfficialRedfoxConfig,
} from "../../types";

const { Text, Paragraph } = Typography;
const { RangePicker } = DatePicker;
const { TextArea } = Input;

const cardStyle = { background: "#1f1f1f", borderColor: "#303030" };
const DEFAULT_MIN_READ = 100000;
const MAX_BATCH_KEYWORDS = 5;

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

type RedfoxMode = "keyword" | "batch" | "account" | "url";

type KeywordForm = {
  keyword: string;
  pages: number;
  min_read_count: number;
};

type BatchKeywordsForm = {
  keywords: string;
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

type BatchKeywordResult = {
  keyword: string;
  status: "succeeded" | "failed";
  summary?: WechatOfficialRedfoxCollectResponse["summary"];
  error?: string;
};

type DraftTemplate = {
  key: string;
  name: string;
  rewrite_style: string;
  target_audience: string;
  call_to_action: string;
  template_instruction: string;
  opening_angle: string;
};

type WechatOfficialSection = "dashboard" | "accounts" | "discovery" | "library" | "drafts" | "settings";

const SECTION_COPY: Record<WechatOfficialSection, { title: string; description: string }> = {
  dashboard: {
    title: "公众号运营总览",
    description: "汇总 Redfox 配置、候选文章、选题池和 blocked 动作状态。",
  },
  accounts: {
    title: "公众号账号矩阵",
    description: "查看公众号账号接入状态；真实授权和发布动作仍保持阻断。",
  },
  discovery: {
    title: "公众号爆文发现",
    description: "通过关键词、公众号或文章 URL 收集爆文候选。",
  },
  library: {
    title: "公众号内容库",
    description: "管理已收集的公众号文章，补全正文、图片和评论素材。",
  },
  drafts: {
    title: "公众号草稿工坊",
    description: "基于爆文拆解生成二创草稿，并只执行 dry-run 校验。",
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

const POOL_STATUS_OPTIONS: Array<{ value: WechatOfficialPoolStatus; label: string; color: string }> = [
  { value: "candidate", label: "候选", color: "blue" },
  { value: "shortlisted", label: "已入选", color: "green" },
  { value: "analyzing", label: "拆解中", color: "gold" },
  { value: "draft_ready", label: "草稿已生成", color: "purple" },
  { value: "rejected", label: "已拒绝", color: "red" },
  { value: "archived", label: "已归档", color: "default" },
];

const WECHAT_DRAFT_TEMPLATES: DraftTemplate[] = [
  {
    key: "case_rewrite",
    name: "案例拆解",
    rewrite_style: "保留爆文结构，提炼可复用案例价值",
    target_audience: "私域运营和内容负责人",
    call_to_action: "关注后续更新",
    template_instruction: "按 背景-冲突-方法-结果-启发 组织二创草稿。",
    opening_angle: "从爆文结构拆解可复用方法",
  },
  {
    key: "insight_commentary",
    name: "观点评论",
    rewrite_style: "提炼核心观点，加入克制评论",
    target_audience: "行业观察者和管理者",
    call_to_action: "欢迎留言交流",
    template_instruction: "按 现象-判断-原因-建议 组织公众号评论稿。",
    opening_angle: "用运营视角解释这篇文章为什么能传播",
  },
  {
    key: "practical_guide",
    name: "实操清单",
    rewrite_style: "转成可执行方法论",
    target_audience: "一线运营和创业者",
    call_to_action: "收藏并复盘自己的业务",
    template_instruction: "按 问题-步骤-注意事项-复盘清单 组织。",
    opening_angle: "把爆文观点转成可落地的操作步骤",
  },
];

function statusColor(status?: string): string {
  if (!status) return "default";
  if (["blocked", "expired", "invalid", "failed", "rejected"].includes(status)) return "red";
  if (["planned", "partial", "pending", "unknown", "analyzing"].includes(status)) return "gold";
  if (["available", "valid", "active", "succeeded", "completed", "shortlisted"].includes(status)) return "green";
  if (["draft_ready"].includes(status)) return "purple";
  return "default";
}

function readCount(article: WechatOfficialContentLibraryItem): number {
  return Number(article.latest_metric?.read_count ?? 0);
}

function poolStatus(article: WechatOfficialContentLibraryItem): string {
  return String(article.analysis?.pool_status || article.analysis?.recommendation_status || "candidate");
}

function poolStatusLabel(status?: string): string {
  return POOL_STATUS_OPTIONS.find((item) => item.value === status)?.label || status || "候选";
}

function lowFollowerLabel(article: WechatOfficialContentLibraryItem): string {
  const value = article.analysis?.low_follower_evidence;
  if (value === "manual") return "人工确认";
  if (value === "inferred") return "Redfox 推断";
  if (value === true) return "已有证据";
  if (value === false) return "无证据";
  return "未知";
}

function articleCoverUrl(article: WechatOfficialContentLibraryItem): string {
  return article.cover_url || "";
}

function formatMetric(value: number | undefined | null): string {
  const numeric = Number(value ?? 0);
  if (numeric >= 10000) return `${(numeric / 10000).toFixed(numeric >= 100000 ? 0 : 1)}w`;
  return numeric.toLocaleString();
}

function articleMaterialLabel(article: WechatOfficialContentLibraryItem): string {
  const analysis = article.analysis || {};
  if (analysis.pool_status === "draft_ready") return "草稿已生成";
  if (analysis.analysis_mode) return "已拆解";
  return "待补全";
}

function collectSummaryText(result: WechatOfficialRedfoxCollectResponse | null): string {
  if (!result) return "尚未执行收集";
  const { summary } = result;
  return `拉取 ${summary.fetched}，保存 ${summary.saved}，10万+候选 ${summary.viral_candidates}，重复 ${summary.deduped}，API 调用 ${summary.api_calls}`;
}

function splitKeywords(value: string): string[] {
  return Array.from(new Set(value.split(/[\n,，]/).map((item) => item.trim()).filter(Boolean))).slice(0, MAX_BATCH_KEYWORDS);
}

function draftPayload(template: DraftTemplate): WechatOfficialCreateDraftPayload {
  return {
    rewrite_style: template.rewrite_style,
    target_audience: template.target_audience,
    call_to_action: template.call_to_action,
    template_key: template.key,
    template_name: template.name,
    template_instruction: template.template_instruction,
    opening_angle: template.opening_angle,
  };
}

function jsonBlock(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
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
  const [mode, setMode] = useState<RedfoxMode>("keyword");
  const [poolFilter, setPoolFilter] = useState<string>("all");
  const [selectedTemplateKey, setSelectedTemplateKey] = useState(WECHAT_DRAFT_TEMPLATES[0].key);
  const [lastCollectResult, setLastCollectResult] = useState<WechatOfficialRedfoxCollectResponse | null>(null);
  const [batchResults, setBatchResults] = useState<BatchKeywordResult[]>([]);
  const [draftIdByArticle, setDraftIdByArticle] = useState<Record<number, number>>({});
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [refreshingDetail, setRefreshingDetail] = useState(false);
  const [detailActionMessage, setDetailActionMessage] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [contentDetail, setContentDetail] = useState<WechatOfficialContentDetail | null>(null);

  const [configForm] = Form.useForm();
  const [keywordForm] = Form.useForm<KeywordForm>();
  const [batchForm] = Form.useForm<BatchKeywordsForm>();
  const [accountForm] = Form.useForm<AccountForm>();
  const [urlForm] = Form.useForm<UrlForm>();

  const selectedTemplate = WECHAT_DRAFT_TEMPLATES.find((item) => item.key === selectedTemplateKey) || WECHAT_DRAFT_TEMPLATES[0];
  const candidateCount = useMemo(() => contentItems.filter((item) => item.is_candidate).length, [contentItems]);
  const displayedItems = useMemo(() => contentItems.filter((item) => poolFilter === "all" || poolStatus(item) === poolFilter), [contentItems, poolFilter]);
  const configuredText = configured ? `已配置 ${redfoxConfig?.masked_api_key || "****"}` : "未配置";
  const batchKeywords = splitKeywords(String(Form.useWatch("keywords", batchForm) || ""));
  const batchPages = Number(Form.useWatch("pages", batchForm) || 1);

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
      message.error(error instanceof Error ? error.message : "操作失败，请检查输入和后端状态。");
    } finally {
      setBusyAction(null);
    }
  }

  async function openDetail(articleId: number): Promise<void> {
    setDetailOpen(true);
    setDetailLoading(true);
    setDetailError(null);
    setDetailActionMessage(null);
    try {
      setContentDetail(await fetchWechatOfficialContentDetail(articleId));
    } catch (error) {
      setDetailError(error instanceof Error ? error.message : "文章详情读取失败");
      message.error(error instanceof Error ? error.message : "文章详情读取失败");
    } finally {
      setDetailLoading(false);
    }
  }

  async function reloadDetail(): Promise<void> {
    const articleId = contentDetail?.article.id;
    if (articleId) {
      setContentDetail(await fetchWechatOfficialContentDetail(articleId));
    }
  }

  async function handleRefreshDetail(): Promise<void> {
    const articleId = contentDetail?.article.id;
    if (!articleId) return;
    setRefreshingDetail(true);
    setDetailError(null);
    setDetailActionMessage(null);
    try {
      const detail = await refreshWechatOfficialContentDetail(articleId);
      setContentDetail(detail);
      await refreshWorkspace();
      setDetailActionMessage("详情已补全：封面、正文图片和评论以 Redfox 返回为准；未执行素材上传或发布动作。");
    } catch (error) {
      setDetailError(apiErrorMessage(error, "详情补全失败，请确认 Redfox 配置可用且文章 URL 可访问。"));
    } finally {
      setRefreshingDetail(false);
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

  const handleBatchCollect = () => runAction("collect-batch", "批量关键词计划执行完成", async () => {
    const values = await batchForm.validateFields();
    const keywords = splitKeywords(values.keywords);
    if (!keywords.length) throw new Error("请输入至少 1 个关键词");
    const results: BatchKeywordResult[] = [];
    for (const keyword of keywords) {
      try {
        const response = await collectWechatOfficialRedfoxArticles({
          keyword,
          pages: values.pages ?? 1,
          sort_type: "_4",
          min_read_count: values.min_read_count ?? DEFAULT_MIN_READ,
          save_snapshot: true,
        });
        results.push({ keyword, status: "succeeded", summary: response.summary });
        setLastCollectResult(response);
      } catch (error) {
        results.push({ keyword, status: "failed", error: error instanceof Error ? error.message : "收集失败" });
      }
      setBatchResults([...results]);
    }
    await refreshWorkspace();
    if (results.some((item) => item.status === "failed")) {
      message.warning("部分关键词收集失败，已保留成功结果。");
    }
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

  const handleUpdatePoolStatus = (article: WechatOfficialContentLibraryItem, nextStatus: WechatOfficialPoolStatus) => runAction(`status-${article.id}-${nextStatus}`, `已更新为${poolStatusLabel(nextStatus)}`, async () => {
    await updateWechatOfficialRecommendation(article.id, { pool_status: nextStatus });
    await refreshWorkspace();
    if (contentDetail?.article.id === article.id) await reloadDetail();
  });

  const handleAnalyze = (article: WechatOfficialContentLibraryItem) => runAction(`analyze-${article.id}`, "爆点拆解已生成", async () => {
    await analyzeWechatOfficialHotspots(article.id, {});
    await refreshWorkspace();
    if (contentDetail?.article.id === article.id) await reloadDetail();
  });

  const handleCreateDraft = (article: WechatOfficialContentLibraryItem) => runAction(`draft-${article.id}`, `已按「${selectedTemplate.name}」生成公众号二创草稿`, async () => {
    const draft = await createWechatOfficialDraft(article.id, draftPayload(selectedTemplate));
    setDraftIdByArticle((current) => ({ ...current, [article.id]: draft.id }));
    await refreshWorkspace();
    if (contentDetail?.article.id === article.id) await reloadDetail();
  });

  const handleDryRun = (article: WechatOfficialContentLibraryItem) => runAction(`dry-${article.id}`, "dry-run 完成：真实发布和群发保持 blocked", async () => {
    let draftId = draftIdByArticle[article.id];
    if (!draftId) {
      const draft = await createWechatOfficialDraft(article.id, draftPayload(selectedTemplate));
      draftId = draft.id;
      setDraftIdByArticle((current) => ({ ...current, [article.id]: draft.id }));
    }
    const result = await dryRunWechatOfficialDraft(draftId, {});
    if (!result.publish_blocked || !result.sendall_blocked) {
      throw new Error("dry-run 未返回 blocked 状态，请检查后端安全契约。");
    }
    await refreshWorkspace();
  });

  const handleMarkManualLowFollower = (article: WechatOfficialContentLibraryItem) => runAction(`low-${article.id}`, "已标记低粉证据为人工确认", async () => {
    await updateWechatOfficialRecommendation(article.id, { low_follower_evidence: "manual", low_follower_note: "人工确认低粉爆文证据" });
    await refreshWorkspace();
  });

  const renderArticleActions = (article: WechatOfficialContentLibraryItem) => [
    <Button key="detail" size="small" onClick={() => void openDetail(article.id)}>详情</Button>,
    <Button key="shortlist" size="small" loading={busyAction === `status-${article.id}-shortlisted`} onClick={() => handleUpdatePoolStatus(article, "shortlisted")}>入选</Button>,
    <Button key="analyze" size="small" loading={busyAction === `analyze-${article.id}`} onClick={() => handleAnalyze(article)}>拆解爆点</Button>,
    <Button key="draft" size="small" loading={busyAction === `draft-${article.id}`} onClick={() => handleCreateDraft(article)}>生成草稿</Button>,
    <Button key="dry" size="small" loading={busyAction === `dry-${article.id}`} onClick={() => handleDryRun(article)}>Dry-run</Button>,
    <Button key="reject" size="small" danger loading={busyAction === `status-${article.id}-rejected`} onClick={() => handleUpdatePoolStatus(article, "rejected")}>拒绝</Button>,
  ];

  return (
    <div>
      <PageHeader
        eyebrow="运营中台 / 微信公众号"
        title={sectionCopy.title}
        description={sectionCopy.description}
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
        description="本页面只做爆文收集、选题池、草稿生成和 dry-run。真实授权、素材上传、草稿同步、预览发送、群发发布没有可执行入口。"
      />

      {showDashboard ? (
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={24} md={8} xl={6}><Card style={cardStyle}><Statistic title="Redfox" value={configuredText} prefix={<SafetyCertificateOutlined />} /></Card></Col>
          <Col xs={24} md={8} xl={6}><Card style={cardStyle}><Statistic title="10万+ 候选" value={candidateCount} prefix={<DatabaseOutlined />} /></Card></Col>
          <Col xs={24} md={8} xl={6}><Card style={cardStyle}><Statistic title="选题池展示" value={displayedItems.length} prefix={<FileTextOutlined />} /></Card></Col>
          <Col xs={24} md={8} xl={6}><Card style={cardStyle}><Statistic title="Blocked actions" value={overview.blocked_actions.length} prefix={<LockOutlined />} /></Card></Col>
        </Row>
      ) : null}

      {showAccounts ? (
        <Card title="公众号账号矩阵" style={{ ...cardStyle, marginBottom: 16 }}>
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
      ) : null}

      <Row gutter={[16, 16]}>
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

        {showDiscovery ? (
          <Col xs={24}>
          <Card title="爆文收集计划" style={cardStyle}>
            <Segmented
              value={mode}
              onChange={(value) => setMode(value as RedfoxMode)}
              options={[{ label: "单关键词", value: "keyword" }, { label: "批量关键词", value: "batch" }, { label: "按公众号", value: "account" }, { label: "文章 URL", value: "url" }]}
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

            {mode === "batch" ? (
              <Form form={batchForm} layout="vertical" initialValues={{ pages: 1, min_read_count: DEFAULT_MIN_READ }}>
                <Form.Item name="keywords" label="批量关键词（最多 5 个，换行或逗号分隔）" rules={[{ required: true, message: "请输入关键词" }]}>
                  <TextArea rows={4} placeholder="私域增长\nAI Agent\n企业微信" />
                </Form.Item>
                <Space wrap>
                  <Form.Item name="pages" label="页数"><InputNumber min={1} max={3} /></Form.Item>
                  <Form.Item name="min_read_count" label="最低阅读"><InputNumber min={0} step={10000} /></Form.Item>
                  <Button type="primary" loading={busyAction === "collect-batch"} onClick={handleBatchCollect}>执行批量收集</Button>
                  <Tag color="gold">预计 API 调用 {batchKeywords.length * batchPages}</Tag>
                </Space>
                {batchResults.length ? (
                  <List
                    size="small"
                    dataSource={batchResults}
                    renderItem={(item) => (
                      <List.Item>
                        <Space wrap>
                          <Tag color={item.status === "succeeded" ? "green" : "red"}>{item.keyword}</Tag>
                          <Text type={item.status === "succeeded" ? undefined : "danger"}>
                            {item.summary ? `拉取 ${item.summary.fetched} / 保存 ${item.summary.saved} / 候选 ${item.summary.viral_candidates} / API ${item.summary.api_calls}` : item.error}
                          </Text>
                        </Space>
                      </List.Item>
                    )}
                  />
                ) : null}
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
            <Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>默认 1 页，最多 3 页；批量关键词会串行执行，避免并发消耗 Redfox API。</Paragraph>
          </Card>
        </Col>
        ) : null}

        {showDiscovery || showLibrary || showDrafts ? (
        <Col xs={24}>
          <Card
            title={showDrafts ? "公众号草稿工坊" : showDiscovery ? "本次收集/已入库候选" : "公众号内容库"}
            style={cardStyle}
            extra={
              <Space wrap>
                <Select value={poolFilter} onChange={setPoolFilter} style={{ width: 140 }} options={[{ value: "all", label: "全部状态" }, ...POOL_STATUS_OPTIONS.map(({ value, label }) => ({ value, label }))]} />
                <Select value={selectedTemplateKey} onChange={setSelectedTemplateKey} style={{ width: 160 }} options={WECHAT_DRAFT_TEMPLATES.map((template) => ({ value: template.key, label: template.name }))} />
              </Space>
            }
          >
            <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
              <Col xs={12} md={6}><Card size="small" style={cardStyle}><Statistic title="已入库" value={contentItems.length} /></Card></Col>
              <Col xs={12} md={6}><Card size="small" style={cardStyle}><Statistic title="当前展示" value={displayedItems.length} /></Card></Col>
              <Col xs={12} md={6}><Card size="small" style={cardStyle}><Statistic title="爆文候选" value={candidateCount} /></Card></Col>
              <Col xs={12} md={6}><Card size="small" style={cardStyle}><Statistic title="视图" value="卡片" /></Card></Col>
            </Row>
            {showDrafts ? <Alert showIcon type="info" message="草稿工坊只生成本地二创草稿" description="真实草稿同步、预览发送和群发发布保持 blocked；Dry-run 只校验安全契约。" style={{ marginBottom: 16 }} /> : null}
            {displayedItems.length === 0 ? (
              <Alert showIcon type="info" message="暂无候选文章" description={showDiscovery ? "执行爆文收集后，保存入库的文章会直接显示在这里。" : "先到爆文发现执行收集，或调整筛选条件。"} />
            ) : (
              <Row gutter={[16, 16]}>
                {displayedItems.map((article) => {
                  const status = poolStatus(article);
                  const coverUrl = articleCoverUrl(article);
                  return (
                    <Col xs={24} sm={12} lg={8} xl={6} key={article.id}>
                      <Card
                        hoverable
                        size="small"
                        style={{ ...cardStyle, height: "100%" }}
                        onClick={() => void openDetail(article.id)}
                        cover={
                          <div style={{ position: "relative", background: "#262626" }}>
                            {coverUrl ? (
                              <img src={coverUrl} alt={article.title || "封面"} referrerPolicy="no-referrer" style={{ width: "100%", aspectRatio: "4 / 3", objectFit: "cover", display: "block" }} />
                            ) : (
                              <div style={{ width: "100%", aspectRatio: "4 / 3", display: "flex", alignItems: "center", justifyContent: "center", color: "rgba(255,255,255,.25)", fontSize: 28 }}><FileTextOutlined /></div>
                            )}
                            <Tag color="green" style={{ position: "absolute", top: 8, left: 8 }}>公众号</Tag>
                            <Tag color={article.is_candidate ? "red" : "default"} style={{ position: "absolute", top: 8, right: 8 }}>{article.is_candidate ? "爆文" : "文章"}</Tag>
                          </div>
                        }
                      >
                        <Space direction="vertical" size={8} style={{ width: "100%" }}>
                          <Text strong ellipsis title={article.title}>{article.title || `Article #${article.id}`}</Text>
                          <Text type="secondary" ellipsis>{article.author_name || "未知公众号"}{article.publish_time_remote ? ` · ${article.publish_time_remote}` : ""}</Text>
                          <Space size={10} wrap style={{ color: "rgba(255,255,255,.55)", fontSize: 12 }}>
                            <span>阅读 {formatMetric(article.latest_metric?.read_count)}</span>
                            <span>赞 {formatMetric(article.latest_metric?.like_count)}</span>
                            <span>评论 {formatMetric(article.latest_metric?.comment_count)}</span>
                          </Space>
                          <Space wrap size={4}>
                            <Tag color={statusColor(status)}>{poolStatusLabel(status)}</Tag>
                            <Tag>{lowFollowerLabel(article)}</Tag>
                            <Tag color="blue">{articleMaterialLabel(article)}</Tag>
                          </Space>
                          <Text type="secondary" ellipsis title={article.digest || article.article_url || ""}>{article.digest || article.article_url || "暂无摘要"}</Text>
                          <Space wrap onClick={(event) => event.stopPropagation()}>
                            <Button size="small" onClick={() => void openDetail(article.id)}>详情</Button>
                            <Button size="small" loading={busyAction === `status-${article.id}-shortlisted`} onClick={() => handleUpdatePoolStatus(article, "shortlisted")}>入选</Button>
                            <Button size="small" loading={busyAction === `analyze-${article.id}`} onClick={() => handleAnalyze(article)}>拆解</Button>
                            <Button size="small" type="primary" loading={busyAction === `draft-${article.id}`} onClick={() => handleCreateDraft(article)}>草稿</Button>
                            {article.article_url ? <Button size="small" href={article.article_url} target="_blank" rel="noreferrer">原文</Button> : null}
                          </Space>
                        </Space>
                      </Card>
                    </Col>
                  );
                })}
              </Row>
            )}
          </Card>
        </Col>
        ) : null}

        {showDashboard ? (
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
        ) : null}
      </Row>

      <Drawer title="公众号文章详情" open={detailOpen} onClose={() => setDetailOpen(false)} width={960} loading={detailLoading}>
        {contentDetail ? (
          <Space direction="vertical" size={16} style={{ width: "100%" }}>
            {detailError ? <Alert showIcon type="error" message="详情操作失败" description={detailError} /> : null}
            {detailActionMessage ? <Alert showIcon type="success" message={detailActionMessage} /> : null}
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="标题">{contentDetail.article.title}</Descriptions.Item>
              <Descriptions.Item label="公众号/作者">{contentDetail.article.author_name || "未知"}</Descriptions.Item>
              <Descriptions.Item label="发布时间">{contentDetail.article.publish_time_remote || "未知"}</Descriptions.Item>
              <Descriptions.Item label="链接">{contentDetail.article.article_url || contentDetail.article.content_url}</Descriptions.Item>
              <Descriptions.Item label="指标">阅读 {contentDetail.latest_metric?.read_count ?? 0} / 点赞 {contentDetail.latest_metric?.like_count ?? 0} / 在看 {contentDetail.latest_metric?.wow_count ?? 0} / 评论 {contentDetail.latest_metric?.comment_count ?? 0} / 分享 {contentDetail.latest_metric?.share_count ?? 0}</Descriptions.Item>
              <Descriptions.Item label="状态"><Tag color={statusColor(poolStatus(contentDetail.article))}>{poolStatusLabel(poolStatus(contentDetail.article))}</Tag></Descriptions.Item>
            </Descriptions>

            <Space wrap>
              <Button loading={refreshingDetail} onClick={() => void handleRefreshDetail()}>补全正文与素材</Button>
              <Button loading={busyAction === `analyze-${contentDetail.article.id}`} onClick={() => handleAnalyze(contentDetail.article)}>拆解爆点</Button>
              <Button type="primary" loading={busyAction === `draft-${contentDetail.article.id}`} onClick={() => handleCreateDraft(contentDetail.article)}>按「{selectedTemplate.name}」生成草稿</Button>
              <Button loading={busyAction === `dry-${contentDetail.article.id}`} onClick={() => handleDryRun(contentDetail.article)}>Dry-run</Button>
            </Space>

            <Alert
              showIcon
              type={contentDetail.detail_status?.has_snapshot ? "success" : "warning"}
              message={contentDetail.detail_status?.has_snapshot ? "详情素材已补全" : "当前仅有列表采集数据"}
              description={`正文 ${contentDetail.detail_status?.has_text ? "已获取" : "未获取"} / 图片 ${contentDetail.detail_status?.image_count ?? 0} 张 / 评论正文 ${contentDetail.detail_status?.comment_count ?? 0} 条。补全只会拉取 Redfox 详情并保存远程 URL，不执行素材上传、草稿同步或发布。`}
            />

            <Card size="small" title="封面与正文图片" style={cardStyle}>
              {contentDetail.images?.length ? (
                <Image.PreviewGroup>
                  <Row gutter={[12, 12]}>
                    {contentDetail.images.map((image, index) => (
                      <Col xs={12} sm={8} md={6} key={`${image.url}-${index}`}>
                        <Card size="small" cover={<Image src={image.url} alt={image.alt || contentDetail.article.title} referrerPolicy="no-referrer" style={{ aspectRatio: "1 / 1", objectFit: "cover" }} />}>
                          <Tag color={image.type === "cover" ? "blue" : "default"}>{image.type === "cover" ? "封面" : "正文图"}</Tag>
                        </Card>
                      </Col>
                    ))}
                  </Row>
                </Image.PreviewGroup>
              ) : <Text type="secondary">暂无封面或正文图片；可点击“补全正文与素材”尝试拉取 Redfox 详情。</Text>}
            </Card>

            <Card size="small" title="正文内容" style={cardStyle}>
              <Paragraph style={{ whiteSpace: "pre-wrap" }}>{contentDetail.latest_snapshot?.text || contentDetail.article.digest || "暂无正文；当前可能只完成了列表采集。"}</Paragraph>
            </Card>

            <Card size="small" title={`评论区（${contentDetail.comments?.total ?? 0}）`} style={cardStyle}>
              {contentDetail.comments?.items?.length ? (
                <List
                  size="small"
                  dataSource={contentDetail.comments.items}
                  renderItem={(comment) => (
                    <List.Item>
                      <Space direction="vertical" size={4} style={{ width: "100%" }}>
                        <Text strong>{comment.user_name || "匿名读者"} <Text type="secondary">赞 {comment.like_count ?? 0}</Text></Text>
                        <Text>{comment.content}</Text>
                        {comment.replies?.length ? <div style={{ paddingLeft: 16, borderLeft: "2px solid #303030" }}>{comment.replies.map((reply, index) => <Paragraph key={index} type="secondary" style={{ marginBottom: 4 }}>{String(reply.user_name || "回复")}：{String(reply.content || "")}</Paragraph>)}</div> : null}
                      </Space>
                    </List.Item>
                  )}
                />
              ) : <Text type="secondary">暂无评论正文。Redfox 可能只返回评论数，不返回评论列表；不会伪造评论内容。</Text>}
            </Card>

            <Card size="small" title="爆点拆解" style={cardStyle}>
              <Descriptions column={1} size="small">
                <Descriptions.Item label="标题钩子">{contentDetail.analysis.hotspot_breakdown?.hook || "待拆解"}</Descriptions.Item>
                <Descriptions.Item label="读者痛点">{contentDetail.analysis.hotspot_breakdown?.pain_point || "待拆解"}</Descriptions.Item>
                <Descriptions.Item label="内容承诺">{contentDetail.analysis.hotspot_breakdown?.promise || "待拆解"}</Descriptions.Item>
                <Descriptions.Item label="可信证据">{contentDetail.analysis.hotspot_breakdown?.credibility || "待拆解"}</Descriptions.Item>
                <Descriptions.Item label="结构路径">{contentDetail.analysis.hotspot_breakdown?.structure || "待拆解"}</Descriptions.Item>
                <Descriptions.Item label="二创角度">{contentDetail.analysis.hotspot_breakdown?.reuse_angle || "待拆解"}</Descriptions.Item>
              </Descriptions>
              <Paragraph type="secondary">模式：{contentDetail.analysis.analysis_mode || "未拆解"}；核心洞察：{contentDetail.analysis.core_insight || "待补充"}</Paragraph>
            </Card>

            <Card size="small" title="摘要" style={cardStyle}><Paragraph>{contentDetail.article.digest || "无摘要"}</Paragraph></Card>

            <Collapse
              items={[
                { key: "html", label: "HTML 快照（文本展示，不执行）", children: <pre style={{ whiteSpace: "pre-wrap" }}>{contentDetail.latest_snapshot?.html || "暂无 HTML 快照"}</pre> },
                { key: "raw", label: "原始数据（已脱敏）", children: <pre style={{ whiteSpace: "pre-wrap" }}>{jsonBlock(contentDetail.raw_json)}</pre> },
              ]}
            />
          </Space>
        ) : <Text type="secondary">请选择文章查看详情。</Text>}
      </Drawer>
    </div>
  );
}
