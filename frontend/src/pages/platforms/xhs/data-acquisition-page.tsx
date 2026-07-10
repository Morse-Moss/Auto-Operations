import {
  CheckCircleOutlined,
  CloudDownloadOutlined,
  DatabaseOutlined,
  ExclamationCircleOutlined,
  EyeOutlined,
  ImportOutlined,
  ReloadOutlined,
  RollbackOutlined,
  SearchOutlined,
  StopOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Empty,
  Form,
  Image,
  Input,
  InputNumber,
  message,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  cancelDataAcquisitionRun,
  createDataAcquisitionRun,
  excludeDataAcquisitionCandidates,
  fetchDataAcquisitionCandidates,
  fetchDataAcquisitionReadiness,
  fetchDataAcquisitionRuns,
  fetchKeywordGroup,
  getUsageLimitError,
  importDataAcquisitionCandidates,
  restoreDataAcquisitionCandidates,
  retryDataAcquisitionRun,
} from "../../../lib/api";
import { useUsageBalance } from "../../../hooks/use-usage-balance";
import type { DataAcquisitionCandidate, DataAcquisitionReadiness, DataAcquisitionRun, KeywordGroupDetail } from "../../../types";
import { XhsCrawlerPage } from "./crawler-page";

const { Text, Title } = Typography;
const candidateStatusOptions = [
  { value: "pending", label: "待确认" },
  { value: "excluded", label: "已排除" },
  { value: "imported", label: "已入库" },
  { value: "all", label: "全部候选" },
];
const candidateSortOptions = [
  { value: "latest", label: "按最新" },
  { value: "engagement", label: "按总互动" },
  { value: "likes", label: "按点赞" },
  { value: "collects", label: "按收藏" },
  { value: "comments", label: "按评论" },
  { value: "shares", label: "按转发" },
];
type CandidateSortBy = (typeof candidateSortOptions)[number]["value"];
const defaultReadiness: DataAcquisitionReadiness = {
  available: false,
  status: "checking",
  message: "正在检查数据获取服务状态。",
  next_action: "",
};

function statusTag(status: string) {
  if (status === "completed") return <Tag color="success">已完成</Tag>;
  if (status === "failed") return <Tag color="error">失败</Tag>;
  if (status === "running") return <Tag color="processing">执行中</Tag>;
  if (status === "pending") return <Tag color="warning">排队中</Tag>;
  if (status === "cancelled") return <Tag>已取消</Tag>;
  return <Tag>{status}</Tag>;
}

function candidateStatusTag(status: string) {
  if (status === "pending") return <Tag color="processing">待确认</Tag>;
  if (status === "imported") return <Tag color="success">已入库</Tag>;
  if (status === "excluded") return <Tag color="default">已排除</Tag>;
  if (status === "expired") return <Tag color="warning">已过期</Tag>;
  return <Tag>{status}</Tag>;
}

function metricText(candidate: DataAcquisitionCandidate): string {
  const metrics = candidate.metrics || {};
  const parts = [
    ["赞", metrics.like_count],
    ["藏", metrics.collect_count],
    ["评", metrics.comment_count],
    ["转", metrics.share_count],
  ]
    .filter(([, value]) => typeof value === "number")
    .map(([label, value]) => `${label} ${value}`);
  return parts.length ? parts.join(" / ") : "-";
}

function runKeyword(run: DataAcquisitionRun): string {
  const keyword = run.params?.keyword;
  return typeof keyword === "string" && keyword.trim() ? keyword : "笔记数据";
}

function parseRunId(value: string | null): number | undefined {
  if (!value) return undefined;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
}

function parseRunIds(value: string | null): number[] {
  if (!value) return [];
  const seen = new Set<number>();
  const result: number[] = [];
  for (const item of value.split(",")) {
    const parsed = Number(item.trim());
    if (Number.isInteger(parsed) && parsed > 0 && !seen.has(parsed)) {
      result.push(parsed);
      seen.add(parsed);
    }
  }
  return result;
}

function parseKeywordGroupId(searchParams: URLSearchParams): number | null {
  const parsedKeywordGroupId = Number(searchParams.get("keyword_group_id") || 0);
  return Number.isFinite(parsedKeywordGroupId) && parsedKeywordGroupId > 0 ? parsedKeywordGroupId : null;
}

export function XhsDataAcquisitionPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [form] = Form.useForm<{ keyword: string; limit: number; sort: string; note_type: string }>();
  const keywordGroupId = parseKeywordGroupId(searchParams);
  const fromAnalysisRecheck = searchParams.get("analysis_recheck") === "1";
  const [runs, setRuns] = useState<DataAcquisitionRun[]>([]);
  const [candidates, setCandidates] = useState<DataAcquisitionCandidate[]>([]);
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<number[]>([]);
  const [candidateStatus, setCandidateStatus] = useState<string>(searchParams.get("status") || "pending");
  const [candidateSortBy, setCandidateSortBy] = useState<CandidateSortBy>(searchParams.get("sort_by") || "latest");
  const [selectedRunId, setSelectedRunId] = useState<number | undefined>(parseRunId(searchParams.get("run_id")));
  const [selectedRunIds, setSelectedRunIds] = useState<number[]>(parseRunIds(searchParams.get("run_ids")));
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [keywordGroupRunning, setKeywordGroupRunning] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [readiness, setReadiness] = useState<DataAcquisitionReadiness>(defaultReadiness);
  const [keywordGroup, setKeywordGroup] = useState<KeywordGroupDetail | null>(null);
  const [keywordGroupError, setKeywordGroupError] = useState<string | null>(null);
  const [keywordGroupStatus, setKeywordGroupStatus] = useState<string | null>(null);
  const usage = useUsageBalance();
  const creditsRemaining = usage.bucketRemaining("credits");
  const keywordGroupKeywordLimit = useMemo(() => {
    const parsed = Number(searchParams.get("keyword_limit") || 0);
    return Number.isFinite(parsed) && parsed > 0 ? Math.min(20, Math.max(1, parsed)) : 20;
  }, [searchParams]);
  const keywordGroupNoteLimit = useMemo(() => {
    const parsed = Number(searchParams.get("max_notes_per_keyword") || 0);
    return Number.isFinite(parsed) && parsed > 0 ? Math.min(50, Math.max(1, parsed)) : 10;
  }, [searchParams]);

  const selectedRun = useMemo(() => runs.find((run) => run.id === selectedRunId), [runs, selectedRunId]);
  const selectedRunLabel = selectedRun ? runKeyword(selectedRun) : selectedRunIds.length ? `关键词组 ${selectedRunIds.length} 个任务` : "";
  const selectableCandidateIds = useMemo(
    () => candidates.filter((candidate) => candidate.status !== "imported").map((candidate) => candidate.id),
    [candidates]
  );
  const selectedPendingCount = useMemo(
    () => candidates.filter((candidate) => selectedCandidateIds.includes(candidate.id) && candidate.status === "pending").length,
    [candidates, selectedCandidateIds]
  );
  const selectedExcludedCount = useMemo(
    () => candidates.filter((candidate) => selectedCandidateIds.includes(candidate.id) && candidate.status === "excluded").length,
    [candidates, selectedCandidateIds]
  );
  const selectedAllPending = selectedCandidateIds.length > 0 && selectedPendingCount === selectedCandidateIds.length;
  const selectedAllExcluded = selectedCandidateIds.length > 0 && selectedExcludedCount === selectedCandidateIds.length;

  function syncUrl(nextRunId: number | undefined, nextStatus: string, nextRunIds = selectedRunIds, nextSortBy = candidateSortBy) {
    const next = new URLSearchParams(searchParams);
    if (nextRunIds.length) {
      next.delete("run_id");
      next.set("run_ids", nextRunIds.join(","));
    } else if (nextRunId) {
      next.set("run_id", String(nextRunId));
      next.delete("run_ids");
    } else {
      next.delete("run_id");
      next.delete("run_ids");
    }
    if (nextStatus && nextStatus !== "pending") next.set("status", nextStatus);
    else next.delete("status");
    if (nextSortBy && nextSortBy !== "latest") next.set("sort_by", nextSortBy);
    else next.delete("sort_by");
    setSearchParams(next, { replace: true });
  }

  async function loadPageData(nextRunId = selectedRunId, nextStatus = candidateStatus, nextRunIds = selectedRunIds, nextSortBy = candidateSortBy) {
    setLoading(true);
    try {
      const statusParam = nextStatus === "all" ? undefined : nextStatus;
      const [readinessPayload, runPage, candidatePage] = await Promise.all([
        fetchDataAcquisitionReadiness(),
        fetchDataAcquisitionRuns({ page_size: 10 }),
        fetchDataAcquisitionCandidates({
          run_id: nextRunIds.length ? undefined : nextRunId,
          run_ids: nextRunIds.length ? nextRunIds : undefined,
          status: statusParam,
          sort_by: nextSortBy,
          page_size: nextRunIds.length ? 500 : 50,
        }),
      ]);
      setReadiness(readinessPayload);
      setRuns(runPage.items);
      setCandidates(candidatePage.items);
      setSelectedCandidateIds((current) => current.filter((id) => candidatePage.items.some((candidate) => candidate.id === id)));
    } catch {
      message.error("数据获取页面加载失败。");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadPageData(selectedRunId, candidateStatus, selectedRunIds, candidateSortBy);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!keywordGroupId) {
      setKeywordGroup(null);
      setKeywordGroupError(null);
      return;
    }
    let cancelled = false;
    setKeywordGroupError(null);
    fetchKeywordGroup(keywordGroupId)
      .then((group) => {
        if (!cancelled) setKeywordGroup(group);
      })
      .catch(() => {
        if (!cancelled) setKeywordGroupError("关键词组加载失败，请返回关键词组页面重试。");
      });
    return () => { cancelled = true; };
  }, [keywordGroupId]);

  function updateCandidateView(
    nextRunId: number | undefined,
    nextStatus = candidateStatus,
    nextRunIds: number[] = [],
    nextSortBy = candidateSortBy,
  ) {
    setSelectedRunId(nextRunId);
    setSelectedRunIds(nextRunIds);
    setCandidateStatus(nextStatus);
    setCandidateSortBy(nextSortBy);
    setSelectedCandidateIds([]);
    syncUrl(nextRunId, nextStatus, nextRunIds, nextSortBy);
    void loadPageData(nextRunId, nextStatus, nextRunIds, nextSortBy);
  }

  async function handleCreateRun(values: { keyword: string; limit: number; sort: string; note_type: string }) {
    if (!readiness.available) {
      message.warning(readiness.message || "数据获取服务未就绪，请联系管理员。");
      return;
    }
    if (creditsRemaining !== null && creditsRemaining < 2) {
      message.warning("积分不足，本次数据获取需要 2 积分。");
      return;
    }
    setRunning(true);
    try {
      const run = await createDataAcquisitionRun({
        acquisition_type: "note_search",
        params: {
          keyword: values.keyword.trim(),
          limit: values.limit,
          sort: values.sort,
          note_type: values.note_type,
        },
      });
      if (run.status === "failed") {
        message.error(run.user_message || "本次数据获取失败，任务已停止。");
      } else {
        message.success(`已获取 ${run.candidate_count} 条待确认候选。`);
      }
      updateCandidateView(run.id, "pending");
    } catch (err) {
      const limitError = getUsageLimitError(err);
      message.error(limitError?.message || "本次数据获取失败，任务已停止。");
      void loadPageData();
    } finally {
      setRunning(false);
    }
  }

  async function handleCreateKeywordGroupRuns() {
    if (!keywordGroup) {
      message.warning("关键词组还没有加载完成。");
      return;
    }
    if (!readiness.available) {
      message.warning(readiness.message || "数据获取服务未就绪，请联系管理员。");
      return;
    }
    const keywords = (keywordGroup.keywords || []).map((keyword) => keyword.trim()).filter(Boolean).slice(0, keywordGroupKeywordLimit);
    if (!keywords.length) {
      message.warning("该关键词组没有可获取的关键词。");
      return;
    }
    const requiredCredits = keywords.length * 2;
    if (creditsRemaining !== null && creditsRemaining < requiredCredits) {
      message.warning(`积分不足，本次预计消耗 ${requiredCredits} 积分。`);
      return;
    }
    setKeywordGroupRunning(true);
    setKeywordGroupStatus(null);
    try {
      const createdRuns: DataAcquisitionRun[] = [];
      for (const keyword of keywords) {
        const run = await createDataAcquisitionRun({
          acquisition_type: "note_search",
          params: {
            keyword,
            limit: keywordGroupNoteLimit,
            sort: "interaction",
            note_type: "all",
          },
        });
        createdRuns.push(run);
      }
      const runIds = createdRuns.map((run) => run.id);
      const candidateCount = createdRuns.reduce((sum, run) => sum + (run.candidate_count || 0), 0);
      setKeywordGroupStatus(`关键词组获取完成：${keywords.length} 个关键词，${candidateCount} 条待确认候选。`);
      if (runIds.length) updateCandidateView(undefined, "pending", runIds);
      else await loadPageData();
    } catch (err) {
      const limitError = getUsageLimitError(err);
      message.error(limitError?.message || "关键词组获取笔记数据失败，任务已停止。");
      await loadPageData();
    } finally {
      setKeywordGroupRunning(false);
    }
  }

  async function handleImportSelected() {
    if (!selectedAllPending) {
      message.warning("请选择待确认候选。");
      return;
    }
    setActionLoading(true);
    try {
      const result = await importDataAcquisitionCandidates({ candidate_ids: selectedCandidateIds });
      message.success(result.message);
      setSelectedCandidateIds([]);
      await loadPageData();
    } catch {
      message.error("候选入库失败，请确认已排除候选已先恢复。");
    } finally {
      setActionLoading(false);
    }
  }

  async function handleExcludeSelected() {
    if (!selectedAllPending) {
      message.warning("请选择待确认候选。");
      return;
    }
    setActionLoading(true);
    try {
      await excludeDataAcquisitionCandidates({ candidate_ids: selectedCandidateIds, reason_code: "manual_exclude" });
      message.success("已排除所选候选。");
      setSelectedCandidateIds([]);
      await loadPageData();
    } catch {
      message.error("排除失败，请稍后重试。");
    } finally {
      setActionLoading(false);
    }
  }

  async function handleRestoreSelected() {
    if (!selectedAllExcluded) {
      message.warning("请选择已排除候选。");
      return;
    }
    setActionLoading(true);
    try {
      await restoreDataAcquisitionCandidates({ candidate_ids: selectedCandidateIds });
      message.success("已恢复所选候选。");
      setSelectedCandidateIds([]);
      await loadPageData();
    } catch {
      message.error("恢复失败，请稍后重试。");
    } finally {
      setActionLoading(false);
    }
  }

  async function handleRetryRun(runId: number) {
    setActionLoading(true);
    try {
      const run = await retryDataAcquisitionRun(runId);
      message.success(`已重新获取 ${run.candidate_count} 条候选。`);
      updateCandidateView(run.id, "pending");
    } catch {
      message.error("重新获取失败，任务已停止。");
    } finally {
      setActionLoading(false);
    }
  }

  async function handleCancelRun(runId: number) {
    setActionLoading(true);
    try {
      const run = await cancelDataAcquisitionRun(runId);
      if (run.cancellation_requested) {
        message.info("已请求取消，当前执行会在安全点停止。");
      } else {
        message.success("已取消任务。");
      }
      await loadPageData();
    } catch {
      message.error("取消失败，请稍后重试。");
    } finally {
      setActionLoading(false);
    }
  }

  const candidateColumns: ColumnsType<DataAcquisitionCandidate> = [
    {
      title: "封面",
      dataIndex: "cover_url",
      width: 88,
      render: (url: string) =>
        url ? (
          <Image width={56} height={56} src={url} style={{ objectFit: "cover", borderRadius: 6 }} />
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={false} />
        ),
    },
    {
      title: "笔记",
      dataIndex: "title",
      render: (_, candidate) => (
        <Space direction="vertical" size={2} style={{ minWidth: 0 }}>
          <Text strong ellipsis style={{ maxWidth: 460 }}>
            {candidate.title || "未命名笔记"}
          </Text>
          <Text type="secondary" ellipsis style={{ maxWidth: 460 }}>
            {candidate.content_excerpt || "暂无正文摘要"}
          </Text>
          <Text type="secondary">{candidate.author_name || "未知作者"}</Text>
        </Space>
      ),
    },
    {
      title: "来源关键词",
      dataIndex: "source_keyword",
      width: 140,
      render: (value: string) => value ? <Tag color="blue">{value}</Tag> : <Text type="secondary">-</Text>,
    },
    { title: "指标", width: 180, render: (_, candidate) => <Text>{metricText(candidate)}</Text> },
    { title: "状态", dataIndex: "status", width: 100, render: candidateStatusTag },
  ];

  return (
    <div>
      <Row justify="space-between" align="middle" gutter={[16, 16]} style={{ marginBottom: 20 }}>
        <Col>
          <Title level={4} style={{ margin: 0 }}>
            小红书数据获取
          </Title>
          <Text type="secondary">先获取候选，再人工确认入库；失败时任务停止，不自动切换其他路径。</Text>
        </Col>
        <Col>
          <Button icon={<ReloadOutlined />} onClick={() => void loadPageData()} loading={loading}>
            刷新
          </Button>
        </Col>
      </Row>

      <Card title={<Space><SearchOutlined />获取笔记数据</Space>} style={{ marginBottom: 20 }}>
        <Alert
          type="info"
          showIcon
          message={`积分余额：${creditsRemaining ?? "加载中"} 积分`}
          description="获取笔记数据每次消耗 2 积分；任务失败会由后端自动退回。"
          style={{ marginBottom: 16 }}
        />
        <Alert
          type={readiness.available ? "info" : "warning"}
          showIcon
          message={readiness.available ? "新数据会进入待确认候选，不会自动进入内容库。" : readiness.message}
          description={!readiness.available && readiness.next_action ? readiness.next_action : undefined}
          style={{ marginBottom: 16 }}
        />
        {keywordGroupId ? (
          <Alert
            type={keywordGroupError ? "error" : fromAnalysisRecheck ? "warning" : "info"}
            showIcon
            message="关键词组获取笔记数据"
            description={
              keywordGroupError
                || (keywordGroup
                  ? `将使用数据账号按「${keywordGroup.name}」前 ${Math.min(keywordGroupKeywordLimit, keywordGroup.keywords.length)} 个关键词获取候选笔记，每个关键词最多 ${keywordGroupNoteLimit} 条，预计消耗 ${Math.min(keywordGroupKeywordLimit, keywordGroup.keywords.length) * 2} 积分。`
                  : "正在加载关键词组...")
            }
            action={keywordGroup ? (
              <Button
                type="primary"
                size="small"
                icon={<CloudDownloadOutlined />}
                loading={keywordGroupRunning}
                disabled={!readiness.available || Boolean(keywordGroupError)}
                onClick={() => void handleCreateKeywordGroupRuns()}
              >
                按关键词组获取
              </Button>
            ) : undefined}
            style={{ marginBottom: 16 }}
          />
        ) : null}
        {keywordGroupStatus ? <Alert type="success" showIcon message={keywordGroupStatus} style={{ marginBottom: 16 }} /> : null}
        <Form
          form={form}
          layout="vertical"
          initialValues={{ limit: 20, sort: "interaction", note_type: "all" }}
          onFinish={(values) => void handleCreateRun(values)}
        >
          <Row gutter={16}>
            <Col xs={24} md={7}>
              <Form.Item label="关键词" name="keyword" rules={[{ required: true, message: "请输入关键词" }]}>
                <Input placeholder="例如：露营、家居收纳" maxLength={80} />
              </Form.Item>
            </Col>
            <Col xs={12} md={3}>
              <Form.Item label="数量" name="limit">
                <InputNumber min={1} max={50} style={{ width: "100%" }} />
              </Form.Item>
            </Col>
            <Col xs={12} md={3}>
              <Form.Item label="排序" name="sort">
                <Select options={[{ value: "interaction", label: "互动优先" }, { value: "latest", label: "最新优先" }]} />
              </Form.Item>
            </Col>
            <Col xs={24} md={4}>
              <Form.Item label="类型" name="note_type">
                <Select options={[{ value: "all", label: "不限" }, { value: "image", label: "图文" }, { value: "video", label: "视频" }]} />
              </Form.Item>
            </Col>
          </Row>
          <Button
            type="primary"
            htmlType="submit"
            icon={<CloudDownloadOutlined />}
            loading={running}
            disabled={!readiness.available || (creditsRemaining !== null && creditsRemaining < 2)}
          >
            创建获取任务（消耗 2 积分）
          </Button>
        </Form>
      </Card>

      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        <Col xs={24} xl={16}>
          <Card
            title={
              <Space>
                <DatabaseOutlined />
                候选列表
                {selectedRunLabel ? <Tag color="blue">{selectedRunLabel}</Tag> : null}
              </Space>
            }
            extra={
              <Space wrap>
                <Select
                  value={candidateStatus}
                  style={{ width: 120 }}
                  options={candidateStatusOptions}
                  onChange={(value) => updateCandidateView(selectedRunId, value, selectedRunIds)}
                />
                <Select
                  value={candidateSortBy}
                  style={{ width: 128 }}
                  options={candidateSortOptions}
                  onChange={(value) => updateCandidateView(selectedRunId, candidateStatus, selectedRunIds, value)}
                />
                <Button icon={<RollbackOutlined />} onClick={() => void handleRestoreSelected()} disabled={!selectedAllExcluded} loading={actionLoading}>
                  恢复
                </Button>
                <Button icon={<StopOutlined />} onClick={() => void handleExcludeSelected()} disabled={!selectedAllPending} loading={actionLoading}>
                  排除
                </Button>
                <Button type="primary" icon={<ImportOutlined />} onClick={() => void handleImportSelected()} disabled={!selectedAllPending} loading={actionLoading}>
                  入库
                </Button>
              </Space>
            }
          >
            <Table<DataAcquisitionCandidate>
              rowKey="id"
              size="small"
              columns={candidateColumns}
              dataSource={candidates}
              loading={loading}
              pagination={{ pageSize: 10 }}
              rowSelection={{
                selectedRowKeys: selectedCandidateIds,
                onChange: (keys) => setSelectedCandidateIds(keys.map(Number)),
                getCheckboxProps: (candidate) => ({ disabled: !selectableCandidateIds.includes(candidate.id) }),
              }}
              locale={{ emptyText: "暂无候选" }}
            />
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card title="最近任务">
            {runs.length ? (
              <Space direction="vertical" style={{ width: "100%" }}>
                {runs.map((run) => (
                  <Card size="small" key={run.id}>
                    <Space direction="vertical" size={6} style={{ width: "100%" }}>
                      <Space wrap>
                        {run.status === "completed" ? <CheckCircleOutlined /> : null}
                        <Text strong>{runKeyword(run)}</Text>
                        {statusTag(run.status)}
                      </Space>
                      <Text type="secondary">
                        候选 {run.candidate_count} 条 / 上限 {run.effective_limit} 条
                      </Text>
                      {run.user_message ? <Text type="danger">{run.user_message}</Text> : null}
                      <Space wrap>
                        <Button size="small" icon={<EyeOutlined />} onClick={() => updateCandidateView(run.id, "pending")}>
                          查看候选
                        </Button>
                        <Tooltip title="按原参数重新获取">
                          <Button
                            size="small"
                            icon={<ReloadOutlined />}
                            disabled={actionLoading || run.status === "running"}
                            onClick={() => void handleRetryRun(run.id)}
                          >
                            重新获取
                          </Button>
                        </Tooltip>
                        <Button
                          size="small"
                          icon={<StopOutlined />}
                          disabled={actionLoading || !["pending", "running"].includes(run.status)}
                          onClick={() => void handleCancelRun(run.id)}
                        >
                          取消
                        </Button>
                      </Space>
                    </Space>
                  </Card>
                ))}
              </Space>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无任务" />
            )}
          </Card>
        </Col>
      </Row>

      <Collapse
        items={[
          {
            key: "direct-xhs-account",
            label: (
              <Space>
                <ExclamationCircleOutlined />
                <Text strong>小红书账号直连</Text>
                <Tag color="warning">高风险</Tag>
              </Space>
            ),
            children: (
              <div>
                <Alert
                  type="warning"
                  showIcon
                  message="该方式依赖小红书账号登录态，可能触发账号风控。建议仅在明确需要时低频使用。"
                  style={{ marginBottom: 16 }}
                />
                <XhsCrawlerPage visibleSource="xhs" />
              </div>
            ),
          },
        ]}
      />

      <div style={{ marginTop: 16 }}>
        <Link to="/platforms/xhs/library">前往内容库</Link>
        <Text type="secondary"> / 入库后可手动进入分析中心生成洞察。</Text>
      </div>
    </div>
  );
}
