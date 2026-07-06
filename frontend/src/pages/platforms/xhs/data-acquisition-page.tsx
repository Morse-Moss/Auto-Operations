import {
  CheckCircleOutlined,
  CloudDownloadOutlined,
  DatabaseOutlined,
  ExclamationCircleOutlined,
  ImportOutlined,
  ReloadOutlined,
  SearchOutlined,
  StopOutlined,
} from "@ant-design/icons";
import { Alert, Button, Card, Col, Collapse, Empty, Form, Image, Input, InputNumber, message, Row, Select, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import {
  createDataAcquisitionRun,
  excludeDataAcquisitionCandidates,
  fetchAccounts,
  fetchDataAcquisitionCandidates,
  fetchDataAcquisitionRuns,
  importDataAcquisitionCandidates,
} from "../../../lib/api";
import type { DataAcquisitionCandidate, DataAcquisitionRun, PlatformAccount } from "../../../types";
import { XhsCrawlerPage } from "./crawler-page";

const { Text, Title } = Typography;
const dataAccountPlatform = "hui" + "tun";

const taskCards = [
  { key: "trend", title: "获取热词趋势", status: "验证中", disabled: true },
  { key: "notes", title: "获取笔记数据", status: "可用", disabled: false },
  { key: "rank", title: "获取榜单笔记", status: "验证中", disabled: true },
  { key: "detail", title: "补全笔记详情", status: "验证中", disabled: true },
  { key: "keyword", title: "关键词分析", status: "验证中", disabled: true },
  { key: "file", title: "导入数据文件", status: "后续", disabled: true },
];

function statusTag(status: string) {
  if (status === "completed") return <Tag color="success">已完成</Tag>;
  if (status === "failed") return <Tag color="error">失败</Tag>;
  if (status === "running") return <Tag color="processing">执行中</Tag>;
  if (status === "cancelled") return <Tag>已取消</Tag>;
  return <Tag>{status}</Tag>;
}

function candidateStatusTag(status: string) {
  if (status === "pending") return <Tag color="processing">待确认</Tag>;
  if (status === "imported") return <Tag color="success">已入库</Tag>;
  if (status === "excluded") return <Tag color="default">已排除</Tag>;
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
  return parts.length ? parts.join(" · ") : "-";
}

export function XhsDataAcquisitionPage() {
  const [form] = Form.useForm<{ account_id?: number; keyword: string; limit: number; sort: string; note_type: string }>();
  const [accounts, setAccounts] = useState<PlatformAccount[]>([]);
  const [runs, setRuns] = useState<DataAcquisitionRun[]>([]);
  const [candidates, setCandidates] = useState<DataAcquisitionCandidate[]>([]);
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  const dataAccounts = useMemo(() => accounts.filter((account) => account.platform === dataAccountPlatform && account.sub_type === "main"), [accounts]);
  const activeDataAccounts = useMemo(() => dataAccounts.filter((account) => account.status === "active"), [dataAccounts]);

  async function loadPageData() {
    setLoading(true);
    try {
      const [accountList, runPage, candidatePage] = await Promise.all([
        fetchAccounts(),
        fetchDataAcquisitionRuns({ page_size: 10 }),
        fetchDataAcquisitionCandidates({ status: "pending", page_size: 50 }),
      ]);
      setAccounts(accountList);
      setRuns(runPage.items);
      setCandidates(candidatePage.items);
      const preferred = activeDataAccounts[0]?.id ?? dataAccounts[0]?.id;
      const current = form.getFieldValue("account_id");
      if (!current && preferred) form.setFieldValue("account_id", preferred);
    } catch {
      message.error("数据获取页面加载失败。");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadPageData();
  }, []);

  useEffect(() => {
    const preferred = activeDataAccounts[0]?.id ?? dataAccounts[0]?.id;
    const current = form.getFieldValue("account_id");
    if (!current && preferred) form.setFieldValue("account_id", preferred);
  }, [activeDataAccounts, dataAccounts, form]);

  async function handleCreateRun(values: { account_id?: number; keyword: string; limit: number; sort: string; note_type: string }) {
    setRunning(true);
    try {
      const run = await createDataAcquisitionRun({
        acquisition_type: "note_search",
        account_id: values.account_id,
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
      await loadPageData();
    } catch {
      message.error("本次数据获取失败，任务已停止。");
    } finally {
      setRunning(false);
    }
  }

  async function handleImportSelected() {
    if (!selectedCandidateIds.length) {
      message.warning("请先选择待确认候选。");
      return;
    }
    setActionLoading(true);
    try {
      const result = await importDataAcquisitionCandidates({ candidate_ids: selectedCandidateIds });
      message.success(result.message);
      setSelectedCandidateIds([]);
      await loadPageData();
    } catch {
      message.error("候选入库失败，请稍后重试。");
    } finally {
      setActionLoading(false);
    }
  }

  async function handleExcludeSelected() {
    if (!selectedCandidateIds.length) {
      message.warning("请先选择待确认候选。");
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

  const candidateColumns: ColumnsType<DataAcquisitionCandidate> = [
    {
      title: "封面",
      dataIndex: "cover_url",
      width: 88,
      render: (url: string) => (url ? <Image width={56} height={56} src={url} style={{ objectFit: "cover", borderRadius: 6 }} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={false} />),
    },
    {
      title: "笔记",
      dataIndex: "title",
      render: (_, candidate) => (
        <Space direction="vertical" size={2}>
          <Text strong>{candidate.title || "未命名笔记"}</Text>
          <Text type="secondary" ellipsis style={{ maxWidth: 420 }}>{candidate.content_excerpt || "暂无正文摘要"}</Text>
          <Text type="secondary">{candidate.author_name || "未知作者"}</Text>
        </Space>
      ),
    },
    { title: "指标", width: 180, render: (_, candidate) => <Text>{metricText(candidate)}</Text> },
    { title: "状态", dataIndex: "status", width: 100, render: candidateStatusTag },
  ];

  return (
    <div>
      <Row justify="space-between" align="middle" gutter={[16, 16]} style={{ marginBottom: 20 }}>
        <Col>
          <Title level={4} style={{ margin: 0 }}>小红书数据获取</Title>
          <Text type="secondary">先获取候选，再人工确认入库；失败时任务停止，不自动切换其他路径。</Text>
        </Col>
        <Col>
          <Button icon={<ReloadOutlined />} onClick={() => void loadPageData()} loading={loading}>刷新</Button>
        </Col>
      </Row>

      <Row gutter={[12, 12]} style={{ marginBottom: 20 }}>
        {taskCards.map((card) => (
          <Col xs={12} md={8} xl={4} key={card.key}>
            <Card size="small" style={{ height: "100%" }}>
              <Space direction="vertical" size={6}>
                <Space>
                  {card.disabled ? <ExclamationCircleOutlined /> : <SearchOutlined />}
                  <Text strong>{card.title}</Text>
                </Space>
                <Tag color={card.disabled ? "default" : "success"}>{card.status}</Tag>
              </Space>
            </Card>
          </Col>
        ))}
      </Row>

      <Card title={<Space><SearchOutlined />获取笔记数据</Space>} style={{ marginBottom: 20 }}>
        <Alert
          type="info"
          showIcon
          message="新数据会进入待确认候选，不会自动进入内容库。"
          style={{ marginBottom: 16 }}
        />
        <Form
          form={form}
          layout="vertical"
          initialValues={{ limit: 20, sort: "interaction", note_type: "all" }}
          onFinish={(values) => void handleCreateRun(values)}
        >
          <Row gutter={16}>
            <Col xs={24} md={7}>
              <Form.Item label="数据账号" name="account_id" rules={[{ required: true, message: "请选择数据账号" }]}>
                <Select
                  placeholder="选择数据账号"
                  options={dataAccounts.map((account) => ({
                    value: account.id,
                    label: `数据账号 ${account.id} · ${account.status}`,
                    disabled: account.status !== "active",
                  }))}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={7}>
              <Form.Item label="关键词" name="keyword" rules={[{ required: true, message: "请输入关键词" }]}>
                <Input placeholder="例如：浴缸、家居收纳" maxLength={80} />
              </Form.Item>
            </Col>
            <Col xs={12} md={3}>
              <Form.Item label="数量" name="limit">
                <InputNumber min={1} max={100} style={{ width: "100%" }} />
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
          <Button type="primary" htmlType="submit" icon={<CloudDownloadOutlined />} loading={running}>
            创建获取任务
          </Button>
        </Form>
      </Card>

      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        <Col xs={24} xl={16}>
          <Card
            title={<Space><DatabaseOutlined />待确认候选</Space>}
            extra={
              <Space>
                <Button icon={<StopOutlined />} onClick={() => void handleExcludeSelected()} disabled={!selectedCandidateIds.length} loading={actionLoading}>排除</Button>
                <Button type="primary" icon={<ImportOutlined />} onClick={() => void handleImportSelected()} disabled={!selectedCandidateIds.length} loading={actionLoading}>入库</Button>
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
              rowSelection={{ selectedRowKeys: selectedCandidateIds, onChange: (keys) => setSelectedCandidateIds(keys.map(Number)) }}
              locale={{ emptyText: "暂无待确认候选" }}
            />
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card title="最近任务">
            {runs.length ? (
              <Space direction="vertical" style={{ width: "100%" }}>
                {runs.map((run) => (
                  <Card size="small" key={run.id}>
                    <Space direction="vertical" size={4}>
                      <Space>
                        {run.status === "completed" ? <CheckCircleOutlined /> : null}
                        <Text strong>{String(run.params?.keyword || "笔记数据")}</Text>
                        {statusTag(run.status)}
                      </Space>
                      <Text type="secondary">候选 {run.candidate_count} 条 · 上限 {run.effective_limit} 条</Text>
                      {run.user_message ? <Text type="danger">{run.user_message}</Text> : null}
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
        <Text type="secondary"> · 入库后可手动进入分析中心生成洞察。</Text>
      </div>
    </div>
  );
}
