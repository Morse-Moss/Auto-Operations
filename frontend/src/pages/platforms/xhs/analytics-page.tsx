import {
  BarChartOutlined,
  CommentOutlined,
  DownloadOutlined,
  FileTextOutlined,
  FireOutlined,
  PlusOutlined,
  ReloadOutlined,
  TagsOutlined,
  UserOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Avatar,
  Button,
  Card,
  Col,
  Collapse,
  Descriptions,
  Divider,
  Drawer,
  Empty,
  Form,
  Input,
  List,
  Progress,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Steps,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { PageHeader } from "../../../components/layout/app-shell";
import { useUsageBalance } from "../../../hooks/use-usage-balance";
import {
  checkXhsAnalysisHealth,
  createXhsAnalysisDrafts,
  apiErrorMessage,
  createXhsAnalysisReport,
  createXhsAnalyticsReport,
  downloadExportFile,
  getUsageLimitError,
  fetchKeywordGroups,
  fetchSavedNote,
  fetchXhsAnalysisReport,
  fetchXhsAnalysisReports,
  fetchXhsCommentInsights,
  fetchXhsHotTopics,
  fetchXhsOverview,
  fetchXhsTopContent,
  rerunXhsAnalysisReport,
} from "../../../lib/api";
import type {
  AnalysisDataHealth,
  AnalysisReport,
  AnalyticsCommentInsight,
  AnalyticsHotTopic,
  AnalyticsTopContent,
  DashboardOverview,
  KeywordGroup,
  SavedNote,
  TopicCard,
} from "../../../types";

const { Paragraph, Text } = Typography;
const { TextArea } = Input;

const fallbackOverview: DashboardOverview = {
  platform: "xhs",
  today_crawls: 0,
  saved_notes: 0,
  pending_publishes: 0,
  healthy_accounts: 0,
  at_risk_accounts: 0,
  comment_count: 0,
  total_engagement: 0,
  hot_topics: [],
  recent_activity: [],
};

const fallbackComments: AnalyticsCommentInsight = {
  total_comments: 0,
  question_count: 0,
  top_terms: [],
  top_comments: [],
};

const wizardSteps = [
  { title: "选择范围" },
  { title: "数据健康与样本预览" },
  { title: "生成确认" },
];

const statusColorMap: Record<AnalysisReport["status"], string> = {
  pending: "default",
  running: "processing",
  completed: "success",
  failed: "error",
};

const healthColorMap: Record<AnalysisDataHealth["status"], string> = {
  insufficient: "error",
  minimum: "warning",
  standard: "success",
};

function formatNumber(value = 0): string {
  return value.toLocaleString();
}

function formatDate(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function splitLines(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function splitTags(value: string): string[] {
  return value
    .split(/[,，\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function evidenceLabel(evidenceId: string): string {
  if (evidenceId.startsWith("note:")) return "笔记";
  if (evidenceId.startsWith("comment:")) return "评论";
  if (evidenceId.startsWith("keyword:")) return "关键词";
  if (evidenceId.startsWith("metric:")) return "指标";
  return "证据";
}

function noteIdFromEvidenceId(evidenceId: string): number | null {
  const match = evidenceId.match(/^note:(\d+)$/);
  return match ? Number(match[1]) : null;
}

function getEvidenceNoteId(report: AnalysisReport, evidenceId: string): number | null {
  const directNoteId = noteIdFromEvidenceId(evidenceId);
  if (directNoteId) return directNoteId;
  const commentIdMatch = evidenceId.match(/^comment:(\d+)$/);
  if (!commentIdMatch) return null;
  const comment = report.evidence_pool.comments.find((item) => item.evidence_id === evidenceId);
  return comment?.note_id ?? null;
}

function getNoteUrl(note: SavedNote): string {
  const raw = note.raw_json ?? {};
  for (const key of ["note_url", "url", "share_url"]) {
    const value = raw[key];
    if (typeof value === "string" && value.startsWith("http")) return value;
  }
  const data = (raw.data && typeof raw.data === "object") ? raw.data as Record<string, unknown> : {};
  const items = Array.isArray(data.items) ? data.items : [];
  const item = (items[0] && typeof items[0] === "object") ? items[0] as Record<string, unknown> : {};
  const card = (item.note_card && typeof item.note_card === "object") ? item.note_card as Record<string, unknown> : {};
  for (const obj of [card, item]) {
    const xsec = obj.xsec_token;
    if (typeof xsec === "string" && xsec) {
      const source = (typeof obj.xsec_source === "string" ? obj.xsec_source : "") || "pc_feed";
      return `https://www.xiaohongshu.com/explore/${note.note_id}?xsec_token=${xsec}&xsec_source=${source}`;
    }
    for (const key of ["note_url", "url", "share_url"]) {
      const value = obj[key];
      if (typeof value === "string" && value.startsWith("http")) return value;
    }
  }
  return `https://www.xiaohongshu.com/explore/${note.note_id}`;
}

const topContentColumns: ColumnsType<AnalyticsTopContent> = [
  {
    title: "标题",
    dataIndex: "title",
    key: "title",
    ellipsis: true,
    render: (text: string, record: AnalyticsTopContent) => text || record.note_id,
  },
  {
    title: "作者",
    dataIndex: "author_name",
    key: "author_name",
    width: 120,
    render: (text: string) => text || "-",
  },
  {
    title: "赞藏评转",
    key: "stats",
    width: 200,
    render: (_: unknown, record: AnalyticsTopContent) =>
      `${formatNumber(record.likes)} / ${formatNumber(record.collects)} / ${formatNumber(record.comments)} / ${formatNumber(record.shares)}`,
  },
  {
    title: "互动",
    dataIndex: "engagement",
    key: "engagement",
    width: 100,
    render: (value: number) => formatNumber(value),
    sorter: (a: AnalyticsTopContent, b: AnalyticsTopContent) => a.engagement - b.engagement,
  },
];

const metricIconColors = ["#1668dc", "#52c41a", "#faad14", "#eb2f96"];

export function XhsAnalyticsPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [overview, setOverview] = useState<DashboardOverview>(fallbackOverview);
  const [topContent, setTopContent] = useState<AnalyticsTopContent[]>([]);
  const [hotTopics, setHotTopics] = useState<AnalyticsHotTopic[]>([]);
  const [commentInsights, setCommentInsights] =
    useState<AnalyticsCommentInsight>(fallbackComments);
  const [keywordGroups, setKeywordGroups] = useState<KeywordGroup[]>([]);
  const [analysisReports, setAnalysisReports] = useState<AnalysisReport[]>([]);
  const [selectedReport, setSelectedReport] = useState<AnalysisReport | null>(null);
  const [historyDrawerOpen, setHistoryDrawerOpen] = useState(false);
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(null);
  const [evidenceDrawerOpen, setEvidenceDrawerOpen] = useState(false);
  const [evidenceNote, setEvidenceNote] = useState<SavedNote | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  const evidenceRequestSeq = useRef(0);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [keywordGroupId, setKeywordGroupId] = useState<number | undefined>();
  const [excludedNoteIds, setExcludedNoteIds] = useState<number[]>([]);
  const [analysisHealth, setAnalysisHealth] = useState<AnalysisDataHealth | null>(null);
  const [reportTitle, setReportTitle] = useState("小红书分析报告");
  const [prefilledKeywordGroupId, setPrefilledKeywordGroupId] = useState<number | null>(null);
  const [creatingReport, setCreatingReport] = useState(false);
  const [wizardStep, setWizardStep] = useState(0);
  const [checkingHealth, setCheckingHealth] = useState(false);
  const [editedTopicCards, setEditedTopicCards] = useState<Record<string, TopicCard>>({});
  const [creatingDraftCardId, setCreatingDraftCardId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isGeneratingReport, setIsGeneratingReport] = useState(false);
  const [rerunningReportId, setRerunningReportId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reportMessage, setReportMessage] = useState<string | null>(null);
  const usage = useUsageBalance();
  const creditsRemaining = usage.bucketRemaining("credits");

  async function loadAnalysisReports() {
    const reports = await fetchXhsAnalysisReports();
    setAnalysisReports(reports);
    setSelectedReport((current) => {
      if (!current) return reports[0] ?? null;
      return reports.find((report) => report.id === current.id) ?? current;
    });
  }

  async function loadAnalytics() {
    setIsLoading(true);
    setError(null);
    try {
      const [overviewResult, topResult, topicsResult, commentsResult, groupsResult, reportsResult] =
        await Promise.all([
          fetchXhsOverview(),
          fetchXhsTopContent(),
          fetchXhsHotTopics(),
          fetchXhsCommentInsights(),
          fetchKeywordGroups("xhs"),
          fetchXhsAnalysisReports(),
        ]);
      setOverview(overviewResult);
      setTopContent(topResult.items);
      setHotTopics(topicsResult.items);
      setCommentInsights(commentsResult);
      setKeywordGroups(groupsResult.items);
      setAnalysisReports(reportsResult);
      setSelectedReport((current) => {
        if (!current) return reportsResult[0] ?? null;
        return reportsResult.find((report) => report.id === current.id) ?? current;
      });
    } catch {
      setError("小红书分析中心加载失败。");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadAnalytics();
  }, []);

  useEffect(() => {
    const groupId = Number(searchParams.get("keyword_group_id"));
    if (!(groupId > 0)) {
      setPrefilledKeywordGroupId(null);
      return;
    }
    if (prefilledKeywordGroupId === groupId) return;

    const group = keywordGroups.find((item) => item.id === groupId);
    setKeywordGroupId(groupId);
    setReportTitle(group ? `${group.name} - 小红书分析报告` : `小红书分析报告 - 关键词组 ${groupId}`);
    setWizardOpen(true);
    setWizardStep(0);
    setAnalysisHealth(null);
    setExcludedNoteIds([]);
    setPrefilledKeywordGroupId(groupId);
  }, [keywordGroups, prefilledKeywordGroupId, searchParams]);

  useEffect(() => {
    if (!prefilledKeywordGroupId || keywordGroupId !== prefilledKeywordGroupId) return;
    const group = keywordGroups.find((item) => item.id === prefilledKeywordGroupId);
    if (group) {
      setReportTitle(`${group.name} - 小红书分析报告`);
    }
  }, [keywordGroups, keywordGroupId, prefilledKeywordGroupId]);

  useEffect(() => {
    setEditedTopicCards({});
  }, [selectedReport?.id]);

  async function generateReport() {
    setIsGeneratingReport(true);
    setError(null);
    setReportMessage(null);
    try {
      const report = await createXhsAnalyticsReport({ format: "json" });
      await downloadExportFile(report.download_url, report.file_name);
      setReportMessage(`已导出基础运营报告：${report.note_count} 篇笔记`);
    } catch {
      setError("基础运营报告导出失败，请稍后重试。");
    } finally {
      setIsGeneratingReport(false);
    }
  }

  async function handleSelectReport(report: AnalysisReport) {
    setSelectedReport(report);
    setHistoryDrawerOpen(false);
    try {
      const detail = await fetchXhsAnalysisReport(report.id);
      setSelectedReport(detail);
    } catch {
      message.error("分析报告详情加载失败。");
    }
  }

  function openWizard() {
    setWizardOpen(true);
    setWizardStep(0);
    setAnalysisHealth(null);
    setExcludedNoteIds([]);
    if (!reportTitle.trim()) {
      setReportTitle("小红书分析报告");
    }
  }

  async function handleCheckHealth() {
    if (!keywordGroupId) {
      message.warning("请先选择关键词组。");
      return;
    }
    setCheckingHealth(true);
    try {
      const health = await checkXhsAnalysisHealth({
        keyword_group_id: keywordGroupId,
        excluded_note_ids: excludedNoteIds,
      });
      setAnalysisHealth(health);
      setWizardStep(1);
    } catch {
      setAnalysisHealth(null);
      message.error("数据健康检查失败，请确认关键词组存在且已登录。");
    } finally {
      setCheckingHealth(false);
    }
  }

  function handleCollectMissingData() {
    if (!keywordGroupId || !analysisHealth) {
      message.warning("请先选择关键词组并完成数据健康检查。");
      return;
    }
    const params = new URLSearchParams({
      keyword_group_id: String(keywordGroupId),
      analysis_recheck: "1",
    });
    if (analysisHealth.collection_plan.needed) {
      params.set("keyword_limit", String(Math.max(1, analysisHealth.collection_plan.recommended_keywords.length || 3)));
      params.set("max_notes_per_keyword", String(Math.max(5, analysisHealth.collection_plan.recommended_notes_per_keyword || 10)));
      if (analysisHealth.collection_plan.should_collect_comments) {
        params.set("fetch_comments", "1");
      }
    }
    setWizardOpen(false);
    navigate(`/platforms/xhs/crawler?${params.toString()}`);
  }

  async function handleCreateAnalysisReport() {
    if (!keywordGroupId || !analysisHealth?.can_generate) return;
    setCreatingReport(true);
    try {
      const report = await createXhsAnalysisReport({
        keyword_group_id: keywordGroupId,
        excluded_note_ids: excludedNoteIds,
        title: reportTitle.trim() || "小红书分析报告",
      });
      setSelectedReport(report);
      await loadAnalysisReports();
      await usage.refresh();
      setWizardOpen(false);
      message.success(report.status === "completed" ? "分析报告已生成" : "分析报告生成失败，请查看原因");
    } catch (err) {
      const limitError = getUsageLimitError(err);
      message.error(limitError?.message || apiErrorMessage(err, "分析报告创建失败，请查看模型配置或稍后重试。"));
      void usage.refresh();
    } finally {
      setCreatingReport(false);
    }
  }

  function updateTopicCard(card: TopicCard, patch: Partial<TopicCard>) {
    setEditedTopicCards((current) => ({
      ...current,
      [card.id]: {
        ...(current[card.id] ?? card),
        ...patch,
      },
    }));
  }

  async function handleRerunReport(report: AnalysisReport) {
    setRerunningReportId(report.id);
    try {
      const next = await rerunXhsAnalysisReport(report.id);
      setSelectedReport(next);
      await loadAnalysisReports();
      await usage.refresh();
      message.success(next.status === "completed" ? "分析报告已重跑" : "分析报告重跑失败，请查看原因");
    } catch (err) {
      const limitError = getUsageLimitError(err);
      message.error(limitError?.message || apiErrorMessage(err, "分析报告重跑失败，请稍后重试。"));
      void usage.refresh();
    } finally {
      setRerunningReportId(null);
    }
  }

  async function handleCreateDraft(card: TopicCard) {
    if (!selectedReport) return;
    const editedCard = editedTopicCards[card.id] ?? card;
    setCreatingDraftCardId(card.id);
    try {
      await createXhsAnalysisDrafts(selectedReport.id, card.id, { topic_cards: [editedCard] });
      message.success("草稿骨架已保存到草稿工坊");
    } catch {
      message.error("草稿骨架保存失败，请稍后重试。");
    } finally {
      setCreatingDraftCardId(null);
    }
  }

  async function openEvidence(evidenceId: string) {
    setSelectedEvidenceId(evidenceId);
    setEvidenceDrawerOpen(true);
    setEvidenceNote(null);
    setEvidenceError(null);
    const requestSeq = evidenceRequestSeq.current + 1;
    evidenceRequestSeq.current = requestSeq;

    if (!selectedReport) {
      setEvidenceLoading(false);
      return;
    }
    const noteId = getEvidenceNoteId(selectedReport, evidenceId);
    if (!noteId) {
      setEvidenceLoading(false);
      return;
    }

    setEvidenceLoading(true);
    try {
      const note = await fetchSavedNote(noteId, true);
      if (evidenceRequestSeq.current === requestSeq) {
        setEvidenceNote(note);
      }
    } catch {
      if (evidenceRequestSeq.current === requestSeq) {
        setEvidenceError("原文笔记加载失败，可以先查看报告内保留的证据摘要。");
      }
    } finally {
      if (evidenceRequestSeq.current === requestSeq) {
        setEvidenceLoading(false);
      }
    }
  }

  const metrics = [
    { label: "内容库笔记", value: overview.saved_notes, icon: <FileTextOutlined /> },
    { label: "总互动", value: overview.total_engagement ?? 0, icon: <BarChartOutlined /> },
    { label: "已存评论", value: overview.comment_count ?? 0, icon: <CommentOutlined /> },
    { label: "话题数", value: hotTopics.length, icon: <TagsOutlined /> },
  ];

  const reportColumns: ColumnsType<AnalysisReport> = [
    {
      title: "报告",
      dataIndex: "title",
      key: "title",
      ellipsis: true,
      render: (text: string, record) => (
        <Button type="link" style={{ padding: 0 }} onClick={() => void handleSelectReport(record)}>
          {text || `报告 #${record.id}`}
        </Button>
      ),
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 96,
      render: (status: AnalysisReport["status"]) => <Tag color={statusColorMap[status]}>{status}</Tag>,
    },
    {
      title: "健康",
      dataIndex: ["data_health", "status"],
      key: "health",
      width: 96,
      render: (_: unknown, record) => {
        const status = record.data_health?.status;
        return status ? <Tag color={healthColorMap[status]}>{status}</Tag> : "-";
      },
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      key: "created_at",
      width: 180,
      render: (value: string) => formatDate(value),
    },
  ];

  const maxTopicEngagement = hotTopics.length > 0
    ? Math.max(...hotTopics.map((t) => t.engagement))
    : 1;

  const termSizes = [18, 16, 15, 14, 13, 12];

  function renderHealthPanel() {
    if (!analysisHealth) {
      return (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="先完成数据健康检查，系统会基于真实关键词组、笔记和评论判断能否生成报告。"
        />
      );
    }

    const metricItems = [
      { label: "有效笔记", value: analysisHealth.metrics.valid_note_count },
      { label: "评论", value: analysisHealth.metrics.comment_count },
      { label: "覆盖关键词", value: analysisHealth.metrics.covered_keyword_count },
      { label: "代表样本", value: analysisHealth.metrics.representative_note_count },
    ];

    return (
      <Space direction="vertical" size="middle" style={{ width: "100%" }}>
        <Alert
          showIcon
          type={analysisHealth.can_generate ? "success" : "warning"}
          message={analysisHealth.can_generate ? "当前数据达到生成门槛" : "当前数据低于最低门槛"}
          description={analysisHealth.can_generate
            ? `健康状态：${analysisHealth.status}，置信度上限：${analysisHealth.confidence_cap}。生成报告将消耗 10 积分（剩余 ${creditsRemaining ?? "加载中"} 积分）。`
            : `健康状态：${analysisHealth.status}，置信度上限：${analysisHealth.confidence_cap}。健康检查不消耗积分。`}
        />
        <Row gutter={[12, 12]}>
          {metricItems.map((item) => (
            <Col span={12} key={item.label}>
              <Card size="small">
                <Statistic title={item.label} value={item.value} />
              </Card>
            </Col>
          ))}
        </Row>
        {analysisHealth.missing.length > 0 && (
          <Card size="small" title="缺口">
            <List
              size="small"
              dataSource={analysisHealth.missing}
              renderItem={(item) => (
                <List.Item>
                  <Text>{item.message}</Text>
                  <Text type="secondary">{item.current} / {item.required}</Text>
                </List.Item>
              )}
            />
          </Card>
        )}
        {analysisHealth.warnings.length > 0 && (
          <Alert
            showIcon
            type="warning"
            message="样本提醒"
            description={analysisHealth.warnings.join("；")}
          />
        )}
        <Card
          size="small"
          title="采集建议"
          extra={analysisHealth.collection_plan.needed ? (
            <Button type="primary" size="small" onClick={handleCollectMissingData}>
              去补采缺失数据
            </Button>
          ) : null}
        >
          {analysisHealth.collection_plan.needed ? (
            <Space direction="vertical" size="small" style={{ width: "100%" }}>
              <Descriptions size="small" column={1}>
                <Descriptions.Item label="为什么不能生成">
                  {analysisHealth.missing.map((item) => item.message).join("；") || "样本未达到最低生成门槛"}
                </Descriptions.Item>
                <Descriptions.Item label="下一步怎么做">
                  到数据抓取页补采关键词组笔记{analysisHealth.collection_plan.should_collect_comments ? "，并打开“同时抓取评论”" : ""}，完成后回到分析中心重新检查。
                </Descriptions.Item>
                <Descriptions.Item label="建议关键词">
                  {analysisHealth.collection_plan.recommended_keywords.length > 0
                    ? analysisHealth.collection_plan.recommended_keywords.map((keyword) => <Tag key={keyword}>{keyword}</Tag>)
                    : "按当前关键词组继续补采"}
                </Descriptions.Item>
                <Descriptions.Item label="每关键词建议补采笔记">
                  {analysisHealth.collection_plan.recommended_notes_per_keyword}
                </Descriptions.Item>
                <Descriptions.Item label="是否建议补采评论">
                  {analysisHealth.collection_plan.should_collect_comments ? "是" : "否"}
                </Descriptions.Item>
              </Descriptions>
              <Alert
                type="info"
                showIcon
                message="点击“去补采缺失数据”会自动带上当前关键词组、建议采集量和评论采集选项。"
              />
            </Space>
          ) : (
            <Text type="secondary">当前样本已达到最低生成门槛。</Text>
          )}
        </Card>
      </Space>
    );
  }

  function renderWizardBody() {
    if (wizardStep === 0) {
      return (
        <Form layout="vertical">
          <Form.Item label="关键词组" required>
            <Select
              placeholder="选择一个真实关键词组"
              value={keywordGroupId}
              onChange={(value) => {
                setKeywordGroupId(value);
                setAnalysisHealth(null);
                const group = keywordGroups.find((item) => item.id === value);
                if (group) setReportTitle(`${group.name} - 小红书分析报告`);
              }}
              options={keywordGroups.map((group) => ({
                label: `${group.name}（${group.keywords.length} 个关键词）`,
                value: group.id,
              }))}
            />
          </Form.Item>
          <Form.Item label="报告标题" required>
            <Input value={reportTitle} onChange={(event) => setReportTitle(event.target.value)} />
          </Form.Item>
          <Alert
            type="info"
            showIcon
            message="样本排除"
            description="Task 10 保留 excludedNoteIds 请求参数；真实笔记排除 UI 留给后续任务实现。"
          />
        </Form>
      );
    }

    if (wizardStep === 1) {
      return renderHealthPanel();
    }

    return (
      <Space direction="vertical" size="middle" style={{ width: "100%" }}>
        <Descriptions bordered size="small" column={1}>
          <Descriptions.Item label="报告标题">{reportTitle || "小红书分析报告"}</Descriptions.Item>
          <Descriptions.Item label="关键词组">
            {keywordGroups.find((group) => group.id === keywordGroupId)?.name ?? keywordGroupId ?? "-"}
          </Descriptions.Item>
          <Descriptions.Item label="排除笔记数">{excludedNoteIds.length}</Descriptions.Item>
          <Descriptions.Item label="健康状态">
            {analysisHealth ? <Tag color={healthColorMap[analysisHealth.status]}>{analysisHealth.status}</Tag> : "未检查"}
          </Descriptions.Item>
          <Descriptions.Item label="模型生成状态">
            {analysisHealth?.can_generate ? "允许调用后端生成报告" : "未达门槛，禁止生成"}
          </Descriptions.Item>
        </Descriptions>
        {!analysisHealth?.can_generate && (
          <Alert
            showIcon
            type="warning"
            message="不能生成报告"
            description={(
              <Space direction="vertical" size="small">
                <Text>数据健康检查未通过，后端不会调用模型，也不会生成假报告。</Text>
                <Button type="primary" onClick={handleCollectMissingData}>去补采缺失数据</Button>
              </Space>
            )}
          />
        )}
      </Space>
    );
  }

  function renderEvidenceTags(evidenceIds: string[]) {
    return (
      <Space wrap>
        {evidenceIds.map((evidenceId) => (
          <Tag
            key={evidenceId}
            style={{ cursor: "pointer" }}
            onClick={() => void openEvidence(evidenceId)}
          >
            {evidenceLabel(evidenceId)} {evidenceId}
          </Tag>
        ))}
      </Space>
    );
  }

  function renderSummaryList(title: string, items: Array<{ id: string; text: string; evidence_ids: string[] }>) {
    return (
      <Card size="small" title={title}>
        <List
          size="small"
          dataSource={items}
          locale={{ emptyText: "暂无" }}
          renderItem={(item) => (
            <List.Item>
              <Space direction="vertical" size={4}>
                <Text>{item.text}</Text>
                {renderEvidenceTags(item.evidence_ids)}
              </Space>
            </List.Item>
          )}
        />
      </Card>
    );
  }

  function renderEvidenceDrawerBody() {
    if (!selectedReport || !selectedEvidenceId) {
      return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未选择证据。" />;
    }

    const noteEvidence = selectedReport.evidence_pool.notes.find((item) => item.evidence_id === selectedEvidenceId);
    const commentEvidence = selectedReport.evidence_pool.comments.find((item) => item.evidence_id === selectedEvidenceId);
    const keywordEvidence = selectedReport.evidence_pool.keywords.find((item) => item.evidence_id === selectedEvidenceId);
    const metricEvidence = selectedReport.evidence_pool.metrics.find((item) => item.evidence_id === selectedEvidenceId);

    return (
      <Space direction="vertical" size="middle" style={{ width: "100%" }}>
        <Tag>{evidenceLabel(selectedEvidenceId)} {selectedEvidenceId}</Tag>
        {evidenceError && <Alert type="warning" showIcon message={evidenceError} />}
        {evidenceLoading && <Spin tip="正在加载原文笔记..." />}

        {noteEvidence && (
          <Card size="small" title={noteEvidence.title || "笔记证据"}>
            <Descriptions size="small" column={1} bordered>
              <Descriptions.Item label="作者">{noteEvidence.author_name || "-"}</Descriptions.Item>
              <Descriptions.Item label="互动">{formatNumber(noteEvidence.engagement)}</Descriptions.Item>
              <Descriptions.Item label="赞藏评转">
                {formatNumber(noteEvidence.likes)} / {formatNumber(noteEvidence.collects)} / {formatNumber(noteEvidence.comments)} / {formatNumber(noteEvidence.shares)}
              </Descriptions.Item>
              <Descriptions.Item label="匹配关键词">
                {noteEvidence.matched_keywords.length > 0 ? noteEvidence.matched_keywords.map((keyword) => <Tag key={keyword}>{keyword}</Tag>) : "-"}
              </Descriptions.Item>
              <Descriptions.Item label="摘要">{noteEvidence.excerpt || "-"}</Descriptions.Item>
            </Descriptions>
          </Card>
        )}

        {commentEvidence && (
          <Card size="small" title="评论证据">
            <Descriptions size="small" column={1} bordered>
              <Descriptions.Item label="评论原文">{commentEvidence.content}</Descriptions.Item>
              <Descriptions.Item label="点赞数">{formatNumber(commentEvidence.like_count)}</Descriptions.Item>
              <Descriptions.Item label="关联笔记">note:{commentEvidence.note_id}</Descriptions.Item>
              <Descriptions.Item label="信号">
                {commentEvidence.signals.length > 0 ? commentEvidence.signals.map((signal) => <Tag key={signal}>{signal}</Tag>) : "-"}
              </Descriptions.Item>
            </Descriptions>
          </Card>
        )}

        {keywordEvidence && (
          <Card size="small" title="关键词证据">
            <Descriptions size="small" column={1} bordered>
              <Descriptions.Item label="关键词">{keywordEvidence.keyword}</Descriptions.Item>
              <Descriptions.Item label="命中笔记">{keywordEvidence.matched_notes}</Descriptions.Item>
              <Descriptions.Item label="命中评论">{keywordEvidence.matched_comments}</Descriptions.Item>
            </Descriptions>
          </Card>
        )}

        {metricEvidence && (
          <Card size="small" title="指标证据">
            <Descriptions size="small" column={1} bordered>
              <Descriptions.Item label="指标名">{metricEvidence.name}</Descriptions.Item>
              <Descriptions.Item label="指标值">{formatNumber(metricEvidence.value)}</Descriptions.Item>
              <Descriptions.Item label="说明">{metricEvidence.description}</Descriptions.Item>
            </Descriptions>
          </Card>
        )}

        {evidenceNote && (
          <Card size="small" title="原文笔记">
            <Space direction="vertical" size="small" style={{ width: "100%" }}>
              <Text strong>{evidenceNote.title || evidenceNote.note_id}</Text>
              <Paragraph style={{ whiteSpace: "pre-wrap" }}>{evidenceNote.content || "暂无正文。"}</Paragraph>
              <Button href={getNoteUrl(evidenceNote)} target="_blank" rel="noreferrer">
                打开小红书原文
              </Button>
            </Space>
          </Card>
        )}
      </Space>
    );
  }

  function renderCompletedReport(report: AnalysisReport) {
    const result = report.result_json;
    if (!result) {
      return <Alert type="warning" showIcon message="报告结果为空" description="后端未返回可展示的结构化结果。" />;
    }

    return (
      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        <Card title="核心总结" style={{ background: "#1f1f1f", borderColor: "#303030" }}>
          <Row gutter={[12, 12]}>
            <Col xs={24} lg={8}>{renderSummaryList("事实", result.summary.facts)}</Col>
            <Col xs={24} lg={8}>{renderSummaryList("推断", result.summary.inferences)}</Col>
            <Col xs={24} lg={8}>{renderSummaryList("建议", result.summary.recommendations)}</Col>
          </Row>
        </Card>

        <Card title="洞察卡" style={{ background: "#1f1f1f", borderColor: "#303030" }}>
          <Row gutter={[12, 12]}>
            {result.insight_cards.map((card) => (
              <Col xs={24} lg={12} key={card.id}>
                <Card size="small" title={card.title} extra={<Tag color="blue">{card.score}</Tag>}>
                  <Space direction="vertical" size="small" style={{ width: "100%" }}>
                    <Text type="secondary">置信度：{card.confidence}｜{card.confidence_reason}</Text>
                    <Progress percent={card.sub_scores.traffic_potential} size="small" format={() => "流量潜力"} />
                    <Progress percent={card.sub_scores.demand_strength} size="small" format={() => "需求强度"} />
                    <Progress percent={card.sub_scores.actionability} size="small" format={() => "可执行性"} />
                    {renderEvidenceTags(card.evidence_ids)}
                  </Space>
                </Card>
              </Col>
            ))}
          </Row>
        </Card>

        <Card title="选题卡与草稿骨架" style={{ background: "#1f1f1f", borderColor: "#303030" }}>
          <Row gutter={[12, 12]}>
            {result.topic_cards.map((card) => {
              const editedCard = editedTopicCards[card.id] ?? card;
              return (
                <Col xs={24} lg={12} key={card.id}>
                  <Card
                    size="small"
                    title={editedCard.title_direction || "未命名选题"}
                    extra={
                      <Button
                        type="primary"
                        size="small"
                        onClick={() => void handleCreateDraft(card)}
                        loading={creatingDraftCardId === card.id}
                      >
                        生成草稿骨架
                      </Button>
                    }
                  >
                    <Form layout="vertical">
                      <Form.Item label="标题方向">
                        <Input
                          value={editedCard.title_direction}
                          onChange={(event) => updateTopicCard(card, { title_direction: event.target.value })}
                        />
                      </Form.Item>
                      <Form.Item label="目标痛点">
                        <TextArea
                          rows={2}
                          value={editedCard.target_pain}
                          onChange={(event) => updateTopicCard(card, { target_pain: event.target.value })}
                        />
                      </Form.Item>
                      <Form.Item label="内容角度">
                        <TextArea
                          rows={2}
                          value={editedCard.content_angle}
                          onChange={(event) => updateTopicCard(card, { content_angle: event.target.value })}
                        />
                      </Form.Item>
                      <Form.Item label="推荐结构（一行一个）">
                        <TextArea
                          rows={3}
                          value={editedCard.recommended_structure.join("\n")}
                          onChange={(event) => updateTopicCard(card, { recommended_structure: splitLines(event.target.value) })}
                        />
                      </Form.Item>
                      <Form.Item label="标签（逗号或换行分隔）">
                        <Input
                          value={editedCard.tags.join("，")}
                          onChange={(event) => updateTopicCard(card, { tags: splitTags(event.target.value) })}
                        />
                      </Form.Item>
                      <Form.Item label="封面建议">
                        <Input
                          value={editedCard.cover_suggestion}
                          onChange={(event) => updateTopicCard(card, { cover_suggestion: event.target.value })}
                        />
                      </Form.Item>
                      <Form.Item label="风险提醒">
                        <TextArea
                          rows={2}
                          value={editedCard.risk_warning}
                          onChange={(event) => updateTopicCard(card, { risk_warning: event.target.value })}
                        />
                      </Form.Item>
                    </Form>
                    {renderEvidenceTags(editedCard.evidence_ids)}
                  </Card>
                </Col>
              );
            })}
          </Row>
        </Card>

        <Collapse
          items={[
            {
              key: "evidence",
              label: "证据池",
              children: (
                <Space direction="vertical" style={{ width: "100%" }}>
                  <Descriptions size="small" column={2} bordered>
                    <Descriptions.Item label="笔记证据">{report.evidence_pool.notes.length}</Descriptions.Item>
                    <Descriptions.Item label="评论证据">{report.evidence_pool.comments.length}</Descriptions.Item>
                    <Descriptions.Item label="关键词证据">{report.evidence_pool.keywords.length}</Descriptions.Item>
                    <Descriptions.Item label="指标证据">{report.evidence_pool.metrics.length}</Descriptions.Item>
                  </Descriptions>
                  <List
                    size="small"
                    dataSource={report.evidence_pool.notes.slice(0, 8)}
                    locale={{ emptyText: "暂无笔记证据" }}
                    renderItem={(note) => (
                      <List.Item>
                        <Space direction="vertical" size={2}>
                          <Text>{note.evidence_id}｜{note.title}</Text>
                          <Text type="secondary">互动 {formatNumber(note.engagement)}｜{note.excerpt}</Text>
                        </Space>
                      </List.Item>
                    )}
                  />
                </Space>
              ),
            },
          ]}
        />

        <Card title="HTML 导出" style={{ background: "#1f1f1f", borderColor: "#303030" }}>
          {report.html_file_path ? (
            <Paragraph copyable={{ text: report.html_file_path }}>
              <Text type="secondary">服务端 HTML 路径：</Text>{report.html_file_path}
            </Paragraph>
          ) : (
            <Text type="secondary">后端未返回 HTML 路径。</Text>
          )}
        </Card>
      </Space>
    );
  }

  function renderReportDetail() {
    if (!selectedReport) {
      return (
        <Card style={{ background: "#1f1f1f", borderColor: "#303030" }}>
          <Empty
            description="还没有分析报告。请选择一个真实关键词组，先做数据健康检查，再生成有证据的洞察卡和选题卡。"
          >
            <Button type="primary" icon={<PlusOutlined />} onClick={openWizard}>创建分析报告</Button>
          </Empty>
        </Card>
      );
    }

    if (selectedReport.status === "failed") {
      return (
        <Card title={selectedReport.title} style={{ background: "#1f1f1f", borderColor: "#303030" }}>
          <Alert
            type="error"
            showIcon
            message="分析报告生成失败"
            description={selectedReport.error_message || "后端未返回失败原因。"}
          />
        </Card>
      );
    }

    if (selectedReport.status !== "completed") {
      return (
        <Card title={selectedReport.title} style={{ background: "#1f1f1f", borderColor: "#303030" }}>
          <Alert
            type="info"
            showIcon
            message={`报告状态：${selectedReport.status}`}
            description="报告尚未完成。请刷新历史列表查看最新状态。"
          />
        </Card>
      );
    }

    return renderCompletedReport(selectedReport);
  }

  return (
    <div>
      <PageHeader
        eyebrow="XHS Analysis Center"
        title="小红书分析中心"
        description="从真实关键词组、笔记和评论生成有证据的洞察卡、选题卡和草稿骨架。"
        action={
          <Space>
            <Button onClick={() => setHistoryDrawerOpen(true)}>
              历史报告 {analysisReports.length}
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openWizard}>
              创建分析报告
            </Button>
            <Button
              icon={<DownloadOutlined />}
              onClick={generateReport}
              loading={isGeneratingReport}
            >
              导出基础报告
            </Button>
            <Button
              icon={<ReloadOutlined />}
              onClick={loadAnalytics}
              loading={isLoading}
            >
              刷新
            </Button>
          </Space>
        }
      />

      {/* ---- Top metric cards ---- */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        {metrics.map((metric, idx) => (
          <Col xs={12} sm={12} md={6} key={metric.label}>
            <Card
              size="small"
              style={{
                background: "#1f1f1f",
                borderColor: "#303030",
                borderTop: `2px solid ${metricIconColors[idx]}`,
              }}
            >
              <Statistic
                title={
                  <span style={{ color: "#8c8c8c", fontSize: 13 }}>{metric.label}</span>
                }
                value={metric.value}
                prefix={
                  <span style={{ color: metricIconColors[idx], marginRight: 4 }}>
                    {metric.icon}
                  </span>
                }
                valueStyle={{ fontSize: 28, fontWeight: 600, color: "#e8e8e8" }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      {error && (
        <Alert
          type="error"
          message={error}
          showIcon
          closable
          style={{ marginBottom: 16 }}
        />
      )}
      {reportMessage && (
        <Alert
          type="success"
          message={reportMessage}
          showIcon
          closable
          style={{ marginBottom: 16 }}
        />
      )}

      {isLoading ? (
        <div style={{ textAlign: "center", padding: 48 }}>
          <Spin tip="正在加载小红书分析中心..." />
        </div>
      ) : (
        <>
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message={`积分余额：${creditsRemaining ?? "加载中"} 积分`}
            description="数据健康检查不扣积分；生成或重跑分析报告各消耗 10 积分，失败会由后端自动退回。"
          />
          <Card
            title="当前报告"
            extra={selectedReport ? (
              <Space>
                <Tag color={statusColorMap[selectedReport.status]}>{selectedReport.status}</Tag>
                <Button
                  size="small"
                  icon={<ReloadOutlined />}
                  loading={rerunningReportId === selectedReport.id}
                  disabled={creditsRemaining !== null && creditsRemaining < 10}
                  onClick={() => void handleRerunReport(selectedReport)}
                >
                  重跑（消耗 10 积分）
                </Button>
              </Space>
            ) : null}
            style={{ background: "#1f1f1f", borderColor: "#303030", minHeight: 300, marginBottom: 24 }}
          >
            {renderReportDetail()}
          </Card>

          <Divider style={{ borderColor: "#303030", margin: "24px 0" }}>
            <Text type="secondary">基础概览</Text>
          </Divider>

          {/* ---- Main 2-column layout ---- */}
          <Row gutter={[16, 16]}>
            {/* Left column: Top Content table */}
            <Col xs={24} lg={16}>
              <Card
                title={
                  <Space>
                    <FireOutlined style={{ color: "#f5222d" }} />
                    <span>高潜内容</span>
                  </Space>
                }
                extra={<Link to="/platforms/xhs/library">进入内容库</Link>}
                style={{ background: "#1f1f1f", borderColor: "#303030", height: "100%" }}
                styles={{ body: { padding: "12px 16px" } }}
              >
                <Table<AnalyticsTopContent>
                  columns={topContentColumns}
                  dataSource={topContent}
                  rowKey="id"
                  size="small"
                  pagination={{ pageSize: 10, size: "small" }}
                  locale={{ emptyText: "暂无保存笔记。" }}
                />
              </Card>
            </Col>

            {/* Right column: Hot Topics + Comment Terms stacked */}
            <Col xs={24} lg={8}>
              <div style={{ display: "flex", flexDirection: "column", gap: 16, height: "100%" }}>
                {/* Hot Topics with progress bars */}
                <Card
                  title={
                    <Space>
                      <TagsOutlined style={{ color: "#1668dc" }} />
                      <span>热点话题</span>
                    </Space>
                  }
                  extra={
                    <Tag color="blue">{hotTopics.length} 个</Tag>
                  }
                  style={{ background: "#1f1f1f", borderColor: "#303030", flex: 1 }}
                  styles={{ body: { padding: "8px 16px", maxHeight: 320, overflowY: "auto" } }}
                >
                  {hotTopics.length === 0 ? (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无标签或话题数据。" />
                  ) : (
                    <List
                      dataSource={hotTopics}
                      split={false}
                      renderItem={(topic) => {
                        const pct = Math.round((topic.engagement / maxTopicEngagement) * 100);
                        return (
                          <List.Item style={{ padding: "8px 0", border: "none" }}>
                            <div style={{ width: "100%" }}>
                              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                                <Text style={{ color: "#e8e8e8", fontSize: 13 }}>#{topic.keyword}</Text>
                                <Text type="secondary" style={{ fontSize: 12 }}>
                                  {topic.notes} 篇 / {formatNumber(topic.engagement)} 互动
                                </Text>
                              </div>
                              <Progress
                                percent={pct}
                                showInfo={false}
                                strokeColor="#1668dc"
                                trailColor="#303030"
                                size="small"
                              />
                            </div>
                          </List.Item>
                        );
                      }}
                    />
                  )}
                </Card>

                {/* Comment Terms - Tag Cloud */}
                <Card
                  title={
                    <Space>
                      <CommentOutlined style={{ color: "#faad14" }} />
                      <span>评论关键词</span>
                    </Space>
                  }
                  extra={
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {commentInsights.question_count} 个提问
                    </Text>
                  }
                  style={{ background: "#1f1f1f", borderColor: "#303030" }}
                  styles={{ body: { padding: "12px 16px" } }}
                >
                  {commentInsights.top_terms.length === 0 ? (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无评论数据。" />
                  ) : (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                      {commentInsights.top_terms.map((term, idx) => {
                        const fontSize = termSizes[Math.min(idx, termSizes.length - 1)];
                        const colors = ["#1668dc", "#13c2c2", "#52c41a", "#faad14", "#eb2f96", "#722ed1"];
                        const color = colors[idx % colors.length];
                        return (
                          <Tag
                            key={term.term}
                            color={color}
                            style={{
                              fontSize,
                              padding: "4px 10px",
                              lineHeight: 1.4,
                              border: "none",
                            }}
                          >
                            {term.term} x{term.count}
                          </Tag>
                        );
                      })}
                    </div>
                  )}
                </Card>
              </div>
            </Col>
          </Row>

          <Divider style={{ borderColor: "#303030", margin: "24px 0" }} />

          {/* ---- Bottom: Top Comments ---- */}
          <Card
            title={
              <Space>
                <CommentOutlined style={{ color: "#52c41a" }} />
                <span>高赞评论</span>
              </Space>
            }
            extra={
              <Tag>{commentInsights.top_comments.length} 条</Tag>
            }
            style={{ background: "#1f1f1f", borderColor: "#303030" }}
            styles={{ body: { padding: "8px 16px" } }}
          >
            <List
              dataSource={commentInsights.top_comments}
              locale={{ emptyText: "暂无已保存评论。" }}
              split={false}
              renderItem={(comment) => (
                <List.Item style={{ padding: "10px 0", borderBottom: "1px solid #262626" }}>
                  <List.Item.Meta
                    avatar={
                      <Avatar
                        size={36}
                        icon={<UserOutlined />}
                        style={{ backgroundColor: "#303030" }}
                      />
                    }
                    title={
                      <Text style={{ color: "#d9d9d9", fontSize: 13 }}>{comment.content}</Text>
                    }
                    description={
                      <Space size={16} style={{ marginTop: 2 }}>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {comment.user_name || "未知用户"}
                        </Text>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {comment.like_count} likes
                        </Text>
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          </Card>
        </>
      )}

      <Drawer
        title="历史分析报告"
        width={720}
        open={historyDrawerOpen}
        onClose={() => setHistoryDrawerOpen(false)}
        destroyOnHidden
      >
        <Table<AnalysisReport>
          columns={reportColumns}
          dataSource={analysisReports}
          rowKey="id"
          size="small"
          pagination={{ pageSize: 8, size: "small" }}
          locale={{ emptyText: "暂无分析报告。" }}
          rowClassName={(record) => record.id === selectedReport?.id ? "ant-table-row-selected" : ""}
          onRow={(record) => ({
            onClick: () => void handleSelectReport(record),
          })}
        />
      </Drawer>

      <Drawer
        title="证据详情"
        width={640}
        open={evidenceDrawerOpen}
        onClose={() => setEvidenceDrawerOpen(false)}
        destroyOnHidden
      >
        {renderEvidenceDrawerBody()}
      </Drawer>

      <Drawer
        title="创建小红书分析报告"
        width={720}
        open={wizardOpen}
        onClose={() => setWizardOpen(false)}
        destroyOnHidden
        footer={
          <Space style={{ width: "100%", justifyContent: "space-between" }}>
            <Button onClick={() => setWizardOpen(false)}>取消</Button>
            <Space>
              {wizardStep > 0 && <Button onClick={() => setWizardStep(wizardStep - 1)}>上一步</Button>}
              {wizardStep === 0 && (
                <Button type="primary" onClick={() => void handleCheckHealth()} loading={checkingHealth}>
                  检查数据健康
                </Button>
              )}
              {wizardStep === 1 && (
                <Button type="primary" onClick={() => setWizardStep(2)} disabled={!analysisHealth}>
                  进入生成确认
                </Button>
              )}
              {wizardStep === 2 && (
                <Button
                  type="primary"
                  onClick={() => void handleCreateAnalysisReport()}
                  loading={creatingReport}
                  disabled={!analysisHealth?.can_generate}
                >
                  生成报告
                </Button>
              )}
            </Space>
          </Space>
        }
      >
        <Space direction="vertical" size="large" style={{ width: "100%" }}>
          <Steps current={wizardStep} items={wizardSteps} />
          {renderWizardBody()}
        </Space>
      </Drawer>
    </div>
  );
}
