import {
  ClockCircleOutlined,
  CloseCircleOutlined,
  DashboardOutlined,
  EyeOutlined,
  ReloadOutlined,
  SyncOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Popconfirm,
  Progress,
  Row,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { PageHeader } from "../../components/layout/app-shell";
import {
  cancelTask,
  fetchSchedulerStatus,
  fetchTasks,
  retryDataAcquisitionRun,
  retryTask,
  runDueTasks,
} from "../../lib/api";
import { formatShanghaiTime } from "../../lib/time";
import type { SchedulerStatus, TaskRecord } from "../../types";

const { Text } = Typography;

const taskTypeLabels: Record<string, string> = {
  ai_rewrite: "AI 改写",
  crawl: "数据抓取",
  publish: "发布任务",
  export: "导出任务",
  creator_publish_scheduler: "定时发布",
  monitoring_refresh: "监控刷新",
  data_acquisition_note_search: "数据获取",
};

function formatTaskTime(value: string): string {
  return formatShanghaiTime(value);
}

function statusColor(status: string): string {
  switch (status) {
    case "running":
      return "processing";
    case "completed":
      return "success";
    case "failed":
    case "exhausted":
      return "error";
    case "cancelled":
      return "default";
    case "pending":
      return "warning";
    default:
      return "default";
  }
}

function dataAcquisitionRunId(task: TaskRecord): number | null {
  if (task.task_type !== "data_acquisition_note_search") return null;
  const runId = task.payload.data_acquisition_run_id;
  return typeof runId === "number" ? runId : null;
}

function dataAcquisitionUrl(task: TaskRecord): string | null {
  if (task.task_type !== "data_acquisition_note_search") return null;
  const url = task.payload.data_acquisition_url;
  return typeof url === "string" && url.startsWith("/platforms/xhs/crawler") ? url : null;
}

export function TaskCenterPage() {
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isActionLoading, setIsActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [schedulerStatus, setSchedulerStatus] =
    useState<SchedulerStatus | null>(null);

  async function loadTasks() {
    setIsLoading(true);
    setError(null);
    try {
      const [taskResult, statusResult] = await Promise.all([
        fetchTasks("xhs"),
        fetchSchedulerStatus(),
      ]);
      setTasks(taskResult.items);
      setSchedulerStatus(statusResult);
    } catch {
      setError("任务列表加载失败。");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadTasks();
  }, []);

  function replaceTask(updatedTask: TaskRecord) {
    setTasks((currentTasks) =>
      currentTasks.map((task) =>
        task.id === updatedTask.id ? updatedTask : task
      )
    );
  }

  async function cancelSelectedTask(taskId: number) {
    setIsActionLoading(true);
    setMessage(null);
    try {
      const updatedTask = await cancelTask(taskId);
      replaceTask(updatedTask);
      if (updatedTask.task_type === "data_acquisition_note_search" && updatedTask.status === "running") {
        setMessage(`任务 #${taskId} 已请求取消，当前执行会在安全点停止。`);
      } else {
        setMessage(`任务 #${taskId} 已取消。`);
      }
    } catch {
      setMessage(`任务 #${taskId} 取消失败。`);
    } finally {
      setIsActionLoading(false);
    }
  }

  async function retrySelectedTask(taskId: number) {
    setIsActionLoading(true);
    setMessage(null);
    try {
      replaceTask(await retryTask(taskId));
      setMessage(`任务 #${taskId} 已重新入队。`);
    } catch {
      setMessage(`任务 #${taskId} 重试失败。`);
    } finally {
      setIsActionLoading(false);
    }
  }

  async function retryDataAcquisitionTask(task: TaskRecord) {
    const runId = dataAcquisitionRunId(task);
    if (!runId) return;
    setIsActionLoading(true);
    setMessage(null);
    try {
      const run = await retryDataAcquisitionRun(runId);
      setMessage(`任务 #${task.id} 已重新获取，生成 ${run.candidate_count} 条候选。`);
      await loadTasks();
    } catch {
      setMessage(`任务 #${task.id} 重新获取失败。`);
    } finally {
      setIsActionLoading(false);
    }
  }

  async function runDueXhsTasks() {
    setIsActionLoading(true);
    setMessage(null);
    try {
      const result = await runDueTasks("xhs", { confirmRealPublish: true });
      setMessage(
        `到期任务执行完成：执行 ${result.executed_count} 个，失败 ${result.failed_count} 个。`
      );
      await loadTasks();
    } catch {
      setMessage("到期任务执行失败。");
    } finally {
      setIsActionLoading(false);
    }
  }

  const columns: ColumnsType<TaskRecord> = [
    {
      title: "类型",
      dataIndex: "task_type",
      key: "task_type",
      width: 140,
      render: (type: string) => taskTypeLabels[type] ?? type,
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (status: string) => (
        <Tag color={statusColor(status)}>{status}</Tag>
      ),
    },
    {
      title: "进度",
      dataIndex: "progress",
      key: "progress",
      width: 160,
      render: (progress: number) => (
        <Progress percent={progress} size="small" />
      ),
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      key: "created_at",
      width: 180,
      render: (value: string) => formatTaskTime(value),
    },
    {
      title: "操作",
      key: "actions",
      width: 280,
      render: (_: unknown, record: TaskRecord) => {
        const acquisitionUrl = dataAcquisitionUrl(record);
        const isDataAcquisition = record.task_type === "data_acquisition_note_search";
        return (
          <Space wrap>
            {acquisitionUrl ? (
              <Link to={acquisitionUrl}>
                <Button size="small" icon={<EyeOutlined />}>
                  查看候选
                </Button>
              </Link>
            ) : null}
            <Button
              size="small"
              icon={<CloseCircleOutlined />}
              disabled={
                isActionLoading ||
                !["pending", "running"].includes(record.status)
              }
              onClick={() => cancelSelectedTask(record.id)}
            >
              取消
            </Button>
            <Button
              size="small"
              icon={<ReloadOutlined />}
              disabled={isActionLoading || (isDataAcquisition ? record.status === "running" : record.status !== "failed")}
              onClick={() => (isDataAcquisition ? retryDataAcquisitionTask(record) : retrySelectedTask(record.id))}
            >
              {isDataAcquisition ? "重新获取" : "重试"}
            </Button>
          </Space>
        );
      },
    },
  ];

  const cardStyle = { background: "#1f1f1f", borderColor: "#303030" };

  return (
    <div>
      <PageHeader
        eyebrow="Automation"
        title="任务中心"
        description="抓取、AI、导出和发布任务的统一队列。"
        action={
          <Space>
            <Popconfirm
              title="确认执行到期真实发布任务？"
              description="该操作会执行已到期的小红书发布任务，并可能向真实账号提交内容。"
              okText="确认执行"
              cancelText="取消"
              onConfirm={runDueXhsTasks}
              disabled={isLoading || isActionLoading}
            >
              <Button
                icon={<ThunderboltOutlined />}
                disabled={isLoading || isActionLoading}
              >
                执行到期任务
              </Button>
            </Popconfirm>
            <Button
              icon={<ReloadOutlined />}
              onClick={loadTasks}
              loading={isLoading}
            >
              刷新
            </Button>
          </Space>
        }
      />

      {error && (
        <Alert
          type="error"
          message={error}
          showIcon
          closable
          style={{ marginBottom: 16 }}
        />
      )}
      {message && (
        <Alert
          type="info"
          message={message}
          showIcon
          closable
          style={{ marginBottom: 16 }}
        />
      )}

      {schedulerStatus && (
        <Card
          title={
            <Space>
              <Text>后台调度</Text>
              <Tag
                color={
                  schedulerStatus.enabled && schedulerStatus.running
                    ? "success"
                    : "default"
                }
              >
                {schedulerStatus.enabled
                  ? schedulerStatus.running
                    ? "运行中"
                    : "已启用"
                  : "未启用"}
              </Tag>
            </Space>
          }
          style={{ ...cardStyle, marginBottom: 24 }}
        >
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={12} sm={6}>
              <Statistic
                title="运行状态"
                value={schedulerStatus.running ? "Running" : "Stopped"}
                prefix={<DashboardOutlined />}
              />
            </Col>
            <Col xs={12} sm={6}>
              <Statistic
                title="调度间隔"
                value={schedulerStatus.interval_seconds}
                suffix="s"
                prefix={<ClockCircleOutlined />}
              />
            </Col>
            <Col xs={12} sm={6}>
              <Statistic
                title="注册任务"
                value={schedulerStatus.jobs.length}
                prefix={<SyncOutlined />}
              />
            </Col>
            <Col xs={12} sm={6}>
              <Statistic
                title="最近记录"
                value={schedulerStatus.recent_tasks.length}
                prefix={<CloseCircleOutlined />}
              />
            </Col>
          </Row>
          {schedulerStatus.jobs.length === 0 ? (
            <Text type="secondary">
              调度器当前未注册后台 job。本地默认关闭，开启需设置
              SCHEDULER_ENABLED=true。
            </Text>
          ) : (
            schedulerStatus.jobs.map((job) => (
              <div key={job.id}>
                <Text type="secondary">
                  {job.id} · 下次运行{" "}
                  {job.next_run_time
                    ? formatTaskTime(job.next_run_time)
                    : "-"}
                </Text>
              </div>
            ))
          )}
        </Card>
      )}

      <Card style={cardStyle}>
        {isLoading ? (
          <div style={{ textAlign: "center", padding: 48 }}>
            <Spin tip="正在加载任务..." />
          </div>
        ) : tasks.length === 0 ? (
          <Empty
            image={<ClockCircleOutlined style={{ fontSize: 48, color: "#555" }} />}
            description={
              <div>
                <Text strong>暂无任务记录</Text>
                <br />
                <Text type="secondary">
                  执行抓取、AI 改写或发布后，任务会出现在这里。
                </Text>
              </div>
            }
          />
        ) : (
          <Table<TaskRecord>
            columns={columns}
            dataSource={tasks}
            rowKey="id"
            size="small"
            pagination={{ pageSize: 20, size: "small" }}
          />
        )}
      </Card>
    </div>
  );
}
