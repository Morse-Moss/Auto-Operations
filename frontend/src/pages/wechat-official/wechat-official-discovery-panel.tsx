import { FileTextOutlined } from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Divider,
  Drawer,
  Form,
  Input,
  InputNumber,
  List,
  message,
  Modal,
  Row,
  Segmented,
  Select,
  Space,
  Statistic,
  Tag,
  Typography,
} from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import {
  collectWechatOfficialRedfoxAccount,
  collectWechatOfficialRedfoxArticles,
  deleteWechatOfficialContentLibraryItem,
  fetchWechatOfficialContentLibrary,
  fetchWechatOfficialRedfoxCollectJobs,
  importWechatOfficialRedfoxUrl,
  updateWechatOfficialRecommendation,
} from "../../lib/api";

import type {
  WechatOfficialContentLibraryItem,
  WechatOfficialCrawlJob,
  WechatOfficialPoolStatus,
  WechatOfficialRedfoxCollectResponse,
} from "../../types";

const { Text, Paragraph } = Typography;
const { RangePicker } = DatePicker;
const { TextArea } = Input;

const cardStyle = { background: "#1f1f1f", borderColor: "#303030" };
const DEFAULT_TARGET_COUNT = 10;
const DEFAULT_MAX_PAGES = 3;
const DEFAULT_MIN_READ = 100000;
const MAX_BATCH_KEYWORDS = 5;

type RedfoxMode = "keyword" | "batch" | "account" | "url";

type KeywordForm = {
  keyword: string;
  target_count: number;
  max_pages: number;
  min_read_count: number;
};

type BatchKeywordsForm = {
  keywords: string;
  target_count: number;
  max_pages: number;
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
};

type BatchKeywordResult = {
  keyword: string;
  status: "succeeded" | "failed";
  summary?: WechatOfficialRedfoxCollectResponse["summary"];
  job?: WechatOfficialRedfoxCollectResponse["job"];
  error?: string;
};

const POOL_STATUS_OPTIONS: Array<{ value: WechatOfficialPoolStatus; label: string; color: string }> = [
  { value: "candidate", label: "候选", color: "blue" },
  { value: "shortlisted", label: "已入库", color: "green" },
  { value: "analyzing", label: "内容库处理中", color: "gold" },
  { value: "draft_ready", label: "内容库已生成草稿", color: "purple" },
  { value: "rejected", label: "已拒绝", color: "red" },
  { value: "archived", label: "已归档", color: "default" },
];

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

function poolStatusLabel(status?: string): string {
  return POOL_STATUS_OPTIONS.find((item) => item.value === status)?.label || status || "候选";
}

function formatMetric(value: number | undefined | null): string {
  const numeric = Number(value ?? 0);
  if (numeric >= 10000) return `${(numeric / 10000).toFixed(numeric >= 100000 ? 0 : 1)}w`;
  return numeric.toLocaleString();
}

function collectSummaryText(result: WechatOfficialRedfoxCollectResponse | null): string {
  if (!result) return "尚未执行收集";
  const { summary } = result;
  const details: string[] = [];

  if (summary.requested_target_count !== undefined) details.push(`目标相关 ${summary.requested_target_count}`);
  if (summary.relevance_matched !== undefined) details.push(`相关命中 ${summary.relevance_matched}`);
  if (summary.filtered !== undefined) details.push(`已过滤 ${summary.filtered}`);
  if (summary.target_reached !== undefined) details.push(summary.target_reached ? "已达目标" : "未达目标");

  const base = `拉取 ${summary.fetched}，保存 ${summary.saved}，候选 ${summary.viral_candidates}，重复 ${summary.deduped}，API 调用 ${summary.api_calls}`;
  return details.length ? `${base}，${details.join("，")}` : base;
}

function splitKeywords(value: string): string[] {
  return Array.from(new Set(value.split(/[\n,，]/).map((item) => item.trim()).filter(Boolean))).slice(0, MAX_BATCH_KEYWORDS);
}

function apiErrorMessage(error: unknown, fallback: string): string {
  if (error && typeof error === "object" && "response" in error) {
    const response = (error as { response?: { data?: { detail?: unknown } } }).response;
    const detail = response?.data?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return error instanceof Error ? error.message : fallback;
}

function candidateSummary(article: WechatOfficialContentLibraryItem): string {
  return article.digest || article.article_url || "暂无摘要";
}

function collectJobParam(job: WechatOfficialCrawlJob, key: string): unknown {
  return job.params?.[key];
}

function jobSourceLabel(job: WechatOfficialCrawlJob): string {
  const source = String(collectJobParam(job, "source") || "");
  if (source === "redfox_keyword") return "关键词";
  if (source === "redfox_account") return "公众号";
  if (source === "redfox_url") return "URL";
  return "Redfox";
}

function formatJobTime(job: WechatOfficialCrawlJob): string {
  return job.finished_at || job.started_at || job.created_at || "";
}

function jobSummary(job: WechatOfficialCrawlJob): string {
  const details = [`拉取 ${job.fetched_count}`, `保存 ${job.saved_count}`];
  const apiCalls = collectJobParam(job, "api_calls");
  const matched = collectJobParam(job, "relevance_matched");
  const filtered = collectJobParam(job, "filtered");
  if (apiCalls !== undefined) details.push(`API ${String(apiCalls)}`);
  if (matched !== undefined) details.push(`相关 ${String(matched)}`);
  if (filtered !== undefined) details.push(`过滤 ${String(filtered)}`);
  return details.join(" / ");
}

export function WechatOfficialDiscoveryPanel() {
  const [items, setItems] = useState<WechatOfficialContentLibraryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [mode, setMode] = useState<RedfoxMode>("keyword");
  const [poolFilter, setPoolFilter] = useState<string>("all");
  const [lastCollectResult, setLastCollectResult] = useState<WechatOfficialRedfoxCollectResponse | null>(null);
  const [jobs, setJobs] = useState<WechatOfficialCrawlJob[]>([]);
  const [jobsLoading, setJobsLoading] = useState(false);
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
  const [batchResults, setBatchResults] = useState<BatchKeywordResult[]>([]);
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedArticle, setSelectedArticle] = useState<WechatOfficialContentLibraryItem | null>(null);
  const [shortlistedArticle, setShortlistedArticle] = useState<WechatOfficialContentLibraryItem | null>(null);
  const [keywordForm] = Form.useForm<KeywordForm>();
  const [batchForm] = Form.useForm<BatchKeywordsForm>();
  const [accountForm] = Form.useForm<AccountForm>();
  const [urlForm] = Form.useForm<UrlForm>();

  const batchKeywords = splitKeywords(String(Form.useWatch("keywords", batchForm) || ""));
  const batchTargetCount = Number(Form.useWatch("target_count", batchForm) || DEFAULT_TARGET_COUNT);
  const batchMaxPages = Number(Form.useWatch("max_pages", batchForm) || DEFAULT_MAX_PAGES);

  const refreshCandidates = useCallback(async (jobIdOverride?: number | null) => {
    setLoading(true);
    try {
      const effectiveJobId = jobIdOverride === undefined ? selectedJobId : jobIdOverride;
      const response = await fetchWechatOfficialContentLibrary({ page_size: 100, job_id: effectiveJobId ?? undefined });
      setItems(response.items);
    } catch (error) {
      message.error(apiErrorMessage(error, "候选文章读取失败"));
    } finally {
      setLoading(false);
    }
  }, [selectedJobId]);

  const refreshJobs = useCallback(async () => {
    setJobsLoading(true);
    try {
      const response = await fetchWechatOfficialRedfoxCollectJobs({ page_size: 20 });
      setJobs(response.items);
    } catch (error) {
      message.error(apiErrorMessage(error, "采集记录读取失败"));
    } finally {
      setJobsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshCandidates();
  }, [refreshCandidates]);

  useEffect(() => {
    void refreshJobs();
  }, [refreshJobs]);

  const discoveryItems = useMemo(
    () => items.filter((item) => {
      const status = poolStatus(item);
      return ["candidate", "shortlisted", "analyzing", "draft_ready"].includes(status) || item.is_candidate;
    }),
    [items],
  );
  const displayedItems = useMemo(
    () => discoveryItems.filter((item) => poolFilter === "all" || poolStatus(item) === poolFilter),
    [discoveryItems, poolFilter],
  );
  const candidateCount = useMemo(
    () => discoveryItems.filter((item) => poolStatus(item) === "candidate" || item.is_candidate).length,
    [discoveryItems],
  );
  const shortlistedCount = useMemo(
    () => discoveryItems.filter((item) => poolStatus(item) === "shortlisted").length,
    [discoveryItems],
  );

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

  const openDetail = (article: WechatOfficialContentLibraryItem) => {
    setSelectedArticle(article);
    setDetailOpen(true);
  };

  const selectCollectJob = (job: WechatOfficialCrawlJob) => {
    setSelectedJobId(job.id);
    void refreshCandidates(job.id);
  };

  const clearCollectJobFilter = () => {
    setSelectedJobId(null);
    void refreshCandidates(null);
  };

  const handleKeywordCollect = () => runAction("collect-keyword", "关键词爆文收集完成", async () => {
    const values = await keywordForm.validateFields();
    const response = await collectWechatOfficialRedfoxArticles({
      keyword: values.keyword,
      target_count: values.target_count ?? DEFAULT_TARGET_COUNT,
      max_pages: values.max_pages ?? DEFAULT_MAX_PAGES,
      sort_type: "_4",
      min_read_count: values.min_read_count ?? DEFAULT_MIN_READ,
      save_snapshot: true,
    });
    setLastCollectResult(response);
    setSelectedJobId(response.job.id);
    await refreshJobs();
    await refreshCandidates(response.job.id);
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
          target_count: values.target_count ?? DEFAULT_TARGET_COUNT,
          max_pages: values.max_pages ?? DEFAULT_MAX_PAGES,
          sort_type: "_4",
          min_read_count: values.min_read_count ?? DEFAULT_MIN_READ,
          save_snapshot: true,
        });
        results.push({ keyword, status: "succeeded", summary: response.summary, job: response.job });
        setLastCollectResult(response);
      } catch (error) {
        results.push({ keyword, status: "failed", error: error instanceof Error ? error.message : "收集失败" });
      }
      setBatchResults([...results]);
    }
    const lastSuccess = [...results].reverse().find((item) => item.status === "succeeded" && item.job);
    if (lastSuccess?.job?.id) {
      setSelectedJobId(lastSuccess.job.id);
      await refreshCandidates(lastSuccess.job.id);
    } else {
      await refreshCandidates();
    }
    await refreshJobs();
    if (results.some((item) => item.status === "failed")) message.warning("部分关键词收集失败，已保留成功结果。");
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
    setSelectedJobId(response.job.id);
    await refreshJobs();
    await refreshCandidates(response.job.id);
  });

  const handleUrlImport = () => runAction("import-url", "文章 URL 已作为候选保存", async () => {
    const values = await urlForm.validateFields();
    const response = await importWechatOfficialRedfoxUrl({
      url: values.url,
      save_snapshot: true,
    });
    setLastCollectResult(response);
    setSelectedJobId(response.job.id);
    await refreshJobs();
    await refreshCandidates(response.job.id);
  });

  const handleShortlist = (article: WechatOfficialContentLibraryItem) => runAction(`status-${article.id}-shortlisted`, "已入库，可去内容库继续补素材、拆解和生成草稿", async () => {
    const updated = await updateWechatOfficialRecommendation(article.id, { pool_status: "shortlisted" });
    setItems((current) => current.map((item) => (item.id === article.id ? updated : item)));
    setSelectedArticle((current) => (current?.id === article.id ? updated : current));
    setShortlistedArticle(updated);
  });

  const handleDeleteArticle = (article: WechatOfficialContentLibraryItem) => {
    Modal.confirm({
      title: "删除这篇候选？",
      content: "删除后会清空该文章记录并记录删除黑名单，同 URL 后续采集会被跳过。",
      okText: "删除",
      okType: "danger",
      cancelText: "取消",
      onOk: () => runAction(`delete-${article.id}`, "候选已删除并加入黑名单", async () => {
        await deleteWechatOfficialContentLibraryItem(article.id);
        setItems((current) => current.filter((item) => item.id !== article.id));
        if (selectedArticle?.id === article.id) {
          setDetailOpen(false);
          setSelectedArticle(null);
        }
      }),
    });
  };

  const renderArticleActions = (article: WechatOfficialContentLibraryItem) => (
    <Space wrap onClick={(event) => event.stopPropagation()}>
      <Button size="small" onClick={() => openDetail(article)}>详情</Button>
      <Button size="small" loading={busyAction === `status-${article.id}-shortlisted`} onClick={() => handleShortlist(article)}>入库</Button>
      <Button size="small" danger loading={busyAction === `delete-${article.id}`} onClick={() => handleDeleteArticle(article)}>删除</Button>
      {article.article_url ? <Button size="small" href={article.article_url} target="_blank" rel="noreferrer">原文</Button> : null}
    </Space>
  );

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card title="爆文收集计划" style={cardStyle}>
        <Segmented
          value={mode}
          onChange={(value) => setMode(value as RedfoxMode)}
          options={[{ label: "单关键词", value: "keyword" }, { label: "批量关键词", value: "batch" }, { label: "按公众号", value: "account" }, { label: "文章 URL", value: "url" }]}
          style={{ marginBottom: 16 }}
        />

        {mode === "keyword" ? (
          <Form form={keywordForm} layout="inline" initialValues={{ target_count: DEFAULT_TARGET_COUNT, max_pages: DEFAULT_MAX_PAGES, min_read_count: DEFAULT_MIN_READ }}>
            <Form.Item name="keyword" rules={[{ required: true, message: "请输入关键词" }]}><Input placeholder="关键词，如 私域增长" /></Form.Item>
            <Form.Item name="target_count" label="目标相关篇数"><InputNumber min={1} max={50} /></Form.Item>
            <Form.Item name="max_pages" label="最多翻页"><InputNumber min={1} max={5} /></Form.Item>
            <Form.Item name="min_read_count" label="最低阅读"><InputNumber min={0} step={10000} /></Form.Item>
            <Form.Item><Button type="primary" loading={busyAction === "collect-keyword"} onClick={handleKeywordCollect}>开始收集爆文</Button></Form.Item>
          </Form>
        ) : null}

        {mode === "batch" ? (
          <Form form={batchForm} layout="vertical" initialValues={{ target_count: DEFAULT_TARGET_COUNT, max_pages: DEFAULT_MAX_PAGES, min_read_count: DEFAULT_MIN_READ }}>
            <Form.Item name="keywords" label="批量关键词（最多 5 个，换行或逗号分隔）" rules={[{ required: true, message: "请输入关键词" }]}>
              <TextArea rows={4} placeholder="私域增长\nAI Agent\n企业微信" />
            </Form.Item>
            <Space wrap>
              <Form.Item name="target_count" label="目标相关篇数"><InputNumber min={1} max={50} /></Form.Item>
              <Form.Item name="max_pages" label="最多翻页"><InputNumber min={1} max={5} /></Form.Item>
              <Form.Item name="min_read_count" label="最低阅读"><InputNumber min={0} step={10000} /></Form.Item>
              <Button type="primary" loading={busyAction === "collect-batch"} onClick={handleBatchCollect}>执行批量收集</Button>
              <Tag color="gold">API 调用上限 {batchKeywords.length * batchMaxPages}</Tag>
              <Tag color="blue">每词目标 {batchTargetCount} 篇</Tag>
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
                        {item.summary ? `拉取 ${item.summary.fetched} / 相关命中 ${item.summary.relevance_matched ?? "-"} / 已过滤 ${item.summary.filtered ?? "-"} / 保存 ${item.summary.saved} / API ${item.summary.api_calls}` : item.error}
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
          <Form form={urlForm} layout="inline">
            <Form.Item name="url" rules={[{ required: true, message: "请输入文章 URL" }]} style={{ minWidth: 420 }}><Input placeholder="https://mp.weixin.qq.com/s/..." /></Form.Item>
            <Form.Item><Button type="primary" loading={busyAction === "import-url"} onClick={handleUrlImport}>直接收集并保存候选</Button></Form.Item>
          </Form>
        ) : null}

        <Divider />
        <Alert showIcon type="success" message="最近一次收集结果" description={collectSummaryText(lastCollectResult)} />
        <Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>系统会先按标题、摘要、正文过滤不相关文章，再在最多翻页范围内尽量补齐目标相关篇数；批量关键词串行执行，避免并发消耗 Redfox API。</Paragraph>
      </Card>

      <Card
        title="采集记录"
        style={cardStyle}
        extra={(
          <Space wrap>
            {selectedJobId ? <Button onClick={clearCollectJobFilter}>查看全部候选</Button> : null}
            <Button loading={jobsLoading} onClick={() => void refreshJobs()}>刷新记录</Button>
          </Space>
        )}
      >
        {jobs.length === 0 ? (
          <Alert showIcon type="info" message="暂无采集记录" description="完成 Redfox 采集后，这里会显示可追溯批次；点击批次可筛选候选池。" />
        ) : (
          <List
            loading={jobsLoading}
            dataSource={jobs}
            renderItem={(job) => (
              <List.Item
                onClick={() => selectCollectJob(job)}
                style={{ cursor: "pointer", background: selectedJobId === job.id ? "rgba(22,119,255,.12)" : undefined, paddingInline: 12 }}
              >
                <Space direction="vertical" size={4} style={{ width: "100%" }}>
                  <Space wrap>
                    <Tag color={statusColor(job.status)}>{job.status}</Tag>
                    <Tag color="blue">{jobSourceLabel(job)}</Tag>
                    <Text strong>{job.keyword || `Job #${job.id}`}</Text>
                    <Text type="secondary">批次 #{job.id}</Text>
                  </Space>
                  <Text type="secondary">{jobSummary(job)}{formatJobTime(job) ? ` · ${formatJobTime(job)}` : ""}</Text>
                </Space>
              </List.Item>
            )}
          />
        )}
      </Card>

      <Card
        title="候选发现池"
        style={cardStyle}
        extra={(
          <Space wrap>
            {selectedJobId ? <Tag color="processing">批次 #{selectedJobId}</Tag> : null}
            <Select value={poolFilter} onChange={setPoolFilter} style={{ width: 140 }} options={[{ value: "all", label: "全部状态" }, ...POOL_STATUS_OPTIONS.map(({ value, label }) => ({ value, label }))]} />
            {selectedJobId ? <Button onClick={clearCollectJobFilter}>清除批次</Button> : null}
            <Button loading={loading} onClick={() => void refreshCandidates()}>刷新候选</Button>
            <Link to="/platforms/wechat-official/library"><Button type="primary">去内容库</Button></Link>
          </Space>
        )}
      >
        <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
          <Col xs={12} md={6}><Card size="small" style={cardStyle}><Statistic title="候选" value={candidateCount} /></Card></Col>
          <Col xs={12} md={6}><Card size="small" style={cardStyle}><Statistic title="已入库" value={shortlistedCount} /></Card></Col>
          <Col xs={12} md={6}><Card size="small" style={cardStyle}><Statistic title="当前展示" value={displayedItems.length} /></Card></Col>
          <Col xs={12} md={6}><Card size="small" style={cardStyle}><Statistic title="视图" value="轻量卡片" /></Card></Col>
        </Row>

        {shortlistedArticle ? (
          <Alert
            showIcon
            type="success"
            style={{ marginBottom: 16 }}
            message={`《${shortlistedArticle.title || `Article #${shortlistedArticle.id}`}》已入库`}
            description="下一步去内容库补素材、拆解爆点并生成公众号草稿。"
            action={<Link to="/platforms/wechat-official/library"><Button size="small" type="primary">去内容库</Button></Link>}
            closable
            onClose={() => setShortlistedArticle(null)}
          />
        ) : null}

        {displayedItems.length === 0 ? (
          <Alert showIcon type="info" message="暂无候选文章" description="执行爆文收集后，候选文章会显示在这里；点击入库后再去内容库补素材、拆解和生成草稿。" />
        ) : (
          <Row gutter={[16, 16]}>
            {displayedItems.map((article) => {
              const status = poolStatus(article);
              return (
                <Col xs={24} sm={12} lg={8} xl={6} key={article.id}>
                  <Card hoverable size="small" style={{ ...cardStyle, height: "100%" }} onClick={() => openDetail(article)}>
                    <Space direction="vertical" size={8} style={{ width: "100%" }}>
                      <Space wrap>
                        <Tag color="green">公众号</Tag>
                        <Tag color={statusColor(status)}>{poolStatusLabel(status)}</Tag>
                        {article.is_candidate ? <Tag color="red">爆文候选</Tag> : null}
                      </Space>
                      <Text strong ellipsis title={article.title}>{article.title || `Article #${article.id}`}</Text>
                      <Text type="secondary" ellipsis>{article.author_name || "未知公众号"}{article.publish_time_remote ? ` · ${article.publish_time_remote}` : ""}</Text>
                      <Space size={10} wrap style={{ color: "rgba(255,255,255,.55)", fontSize: 12 }}>
                        <span>阅读 {formatMetric(article.latest_metric?.read_count)}</span>
                        <span>赞 {formatMetric(article.latest_metric?.like_count)}</span>
                        <span>在看 {formatMetric(article.latest_metric?.wow_count)}</span>
                        <span>评论 {formatMetric(article.latest_metric?.comment_count)}</span>
                      </Space>
                      <Text type="secondary" ellipsis title={candidateSummary(article)}>{candidateSummary(article)}</Text>
                      {renderArticleActions(article)}
                    </Space>
                  </Card>
                </Col>
              );
            })}
          </Row>
        )}
      </Card>

      <Drawer title="候选文章详情" open={detailOpen} onClose={() => setDetailOpen(false)} width={760}>
        {selectedArticle ? (
          <Space direction="vertical" size={16} style={{ width: "100%" }}>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="标题">{selectedArticle.title || `Article #${selectedArticle.id}`}</Descriptions.Item>
              <Descriptions.Item label="公众号">{selectedArticle.author_name || "未知"}</Descriptions.Item>
              <Descriptions.Item label="发布时间">{selectedArticle.publish_time_remote || "未知"}</Descriptions.Item>
              <Descriptions.Item label="链接">{selectedArticle.article_url || selectedArticle.content_url || "无"}</Descriptions.Item>
              <Descriptions.Item label="指标">阅读 {selectedArticle.latest_metric?.read_count ?? 0} / 点赞 {selectedArticle.latest_metric?.like_count ?? 0} / 在看 {selectedArticle.latest_metric?.wow_count ?? 0} / 评论 {selectedArticle.latest_metric?.comment_count ?? 0} / 分享 {selectedArticle.latest_metric?.share_count ?? 0}</Descriptions.Item>
              <Descriptions.Item label="状态"><Tag color={statusColor(poolStatus(selectedArticle))}>{poolStatusLabel(poolStatus(selectedArticle))}</Tag></Descriptions.Item>
              <Descriptions.Item label="摘要">{selectedArticle.digest || "暂无摘要"}</Descriptions.Item>
            </Descriptions>
            <Space wrap>
              <Button loading={busyAction === `status-${selectedArticle.id}-shortlisted`} onClick={() => handleShortlist(selectedArticle)}>入库</Button>
              <Button danger loading={busyAction === `delete-${selectedArticle.id}`} onClick={() => handleDeleteArticle(selectedArticle)}>删除</Button>
              {selectedArticle.article_url ? <Button href={selectedArticle.article_url} target="_blank" rel="noreferrer">打开原文</Button> : null}
              <Link to="/platforms/wechat-official/library"><Button type="primary">去内容库</Button></Link>
            </Space>
            <Alert showIcon type="info" message="这里仅展示轻量候选详情" description="正文素材、图片评论、爆点拆解和草稿生成已收敛到内容库；候选页只负责发现、入库、删除和打开原文。" />
          </Space>
        ) : (
          <Text type="secondary"><FileTextOutlined /> 请选择候选文章查看详情。</Text>
        )}
      </Drawer>
    </Space>
  );
}
