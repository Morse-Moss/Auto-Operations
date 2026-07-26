import {
  CheckCircleOutlined,
  CopyOutlined,
  PlusOutlined,
  StopOutlined,
  UserAddOutlined,
} from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { useEffect, useState } from "react";

import {
  activateAdminInviteCode,
  activateAdminTenant,
  activateAdminUser,
  adjustAdminTenantCredit,
  createAdminInviteCode,
  disableAdminInviteCode,
  disableAdminUser,
  fetchAdminInviteCodes,
  fetchAdminTenants,
  fetchAdminUsers,
  suspendAdminTenant,
} from "../../lib/api";
import type { AdminInviteCode, AdminTenant, AdminUser } from "../../types";

const { Title, Text } = Typography;
const RESUME_INVITE_MAX_USES = 100;

const bucketOptions = [
  { label: "积分", value: "credits" },
];

const creditOperationOptions = [
  { label: "增加积分", value: "grant" },
  { label: "扣减积分", value: "deduct" },
  { label: "重置套餐", value: "reset" },
];

function statusTag(status: string) {
  const color = status === "active" ? "green" : status === "suspended" || status === "disabled" ? "red" : "default";
  return <Tag color={color}>{status}</Tag>;
}

export function BetaAdminPage() {
  const { message } = App.useApp();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [tenants, setTenants] = useState<AdminTenant[]>([]);
  const [invites, setInvites] = useState<AdminInviteCode[]>([]);
  const [loading, setLoading] = useState(false);
  const [creditTenant, setCreditTenant] = useState<AdminTenant | null>(null);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [latestInvite, setLatestInvite] = useState<AdminInviteCode | null>(null);
  const [creatingResumeInvite, setCreatingResumeInvite] = useState(false);
  const [creditForm] = Form.useForm();
  const [inviteForm] = Form.useForm();
  const creditOperation = Form.useWatch("operation", creditForm);

  async function loadAll() {
    setLoading(true);
    try {
      const [userRes, tenantRes, inviteRes] = await Promise.all([
        fetchAdminUsers(),
        fetchAdminTenants(),
        fetchAdminInviteCodes(),
      ]);
      setUsers(userRes.items);
      setTenants(tenantRes.items);
      setInvites(inviteRes.items);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadAll();
  }, []);

  async function toggleTenant(tenant: AdminTenant) {
    if (tenant.status === "suspended") {
      await activateAdminTenant(tenant.id);
    } else {
      await suspendAdminTenant(tenant.id);
    }
    message.success("租户状态已更新");
    await loadAll();
  }

  async function toggleUser(user: AdminUser) {
    if (user.status === "disabled") {
      await activateAdminUser(user.id);
    } else {
      await disableAdminUser(user.id);
    }
    message.success("用户状态已更新");
    await loadAll();
  }

  async function submitCreditAdjustment() {
    const values = await creditForm.validateFields();
    if (!creditTenant) return;
    const operation = values.operation || "grant";
    await adjustAdminTenantCredit(creditTenant.id, {
      bucket: values.bucket,
      operation,
      amount: operation === "reset" ? undefined : values.amount,
      total: operation === "reset" ? values.total : undefined,
      reason: values.reason || "",
    });
    message.success("积分已调整");
    setCreditTenant(null);
    creditForm.resetFields();
    await loadAll();
  }

  async function submitInvite() {
    const values = await inviteForm.validateFields();
    const invite = await createAdminInviteCode({ code: values.code.trim(), max_uses: values.max_uses });
    message.success("邀请码已创建");
    setLatestInvite(invite);
    setInviteOpen(false);
    inviteForm.resetFields();
    await loadAll();
  }

  async function createResumeInvite() {
    setCreatingResumeInvite(true);
    try {
      const invite = await createAdminInviteCode({ max_uses: RESUME_INVITE_MAX_USES });
      setLatestInvite(invite);
      message.success("简历邀请码已生成");
      await loadAll();
    } finally {
      setCreatingResumeInvite(false);
    }
  }

  async function copyInviteCode(invite: AdminInviteCode) {
    if (!navigator.clipboard?.writeText) {
      message.error("当前浏览器无法复制，请手动选择邀请码");
      return;
    }
    await navigator.clipboard.writeText(invite.code);
    message.success("邀请码已复制");
  }

  async function toggleInviteStatus(invite: AdminInviteCode) {
    if (invite.status === "disabled") {
      await activateAdminInviteCode(invite.id);
      message.success("邀请码已恢复");
    } else {
      await disableAdminInviteCode(invite.id);
      message.success("邀请码已停用");
    }
    await loadAll();
  }

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <Text type="secondary" style={{ fontSize: 12, textTransform: "uppercase" }}>Beta Admin</Text>
        <Title level={3} style={{ margin: "4px 0 0" }}>准入与管理开关</Title>
      </div>

      <Tabs
        items={[
          {
            key: "tenants",
            label: "租户",
            children: (
              <Table
                rowKey="id"
                loading={loading}
                dataSource={tenants}
                pagination={false}
                columns={[
                  { title: "ID", dataIndex: "id", width: 80 },
                  { title: "名称", dataIndex: "name" },
                  { title: "Slug", dataIndex: "slug" },
                  { title: "状态", dataIndex: "status", render: statusTag, width: 120 },
                  { title: "成员", dataIndex: "member_count", width: 90 },
                  {
                    title: "操作",
                    width: 240,
                    render: (_, tenant) => (
                      <Space>
                        <Button
                          size="small"
                          onClick={() => {
                            setCreditTenant(tenant);
                            creditForm.setFieldsValue({ bucket: "credits", operation: "grant", amount: undefined, total: undefined, reason: "" });
                          }}
                        >
                          积分
                        </Button>
                        <Popconfirm title="确认切换租户状态？" onConfirm={() => void toggleTenant(tenant)}>
                          <Button size="small" danger={tenant.status !== "suspended"}>
                            {tenant.status === "suspended" ? "解冻" : "冻结"}
                          </Button>
                        </Popconfirm>
                      </Space>
                    ),
                  },
                ]}
              />
            ),
          },
          {
            key: "users",
            label: "用户",
            children: (
              <Table
                rowKey="id"
                loading={loading}
                dataSource={users}
                pagination={false}
                columns={[
                  { title: "ID", dataIndex: "id", width: 80 },
                  { title: "账号", dataIndex: "username" },
                  { title: "角色", dataIndex: "role", render: (role) => <Tag color={role === "admin" ? "blue" : "default"}>{role}</Tag>, width: 120 },
                  { title: "状态", dataIndex: "status", render: statusTag, width: 120 },
                  { title: "租户数", dataIndex: "tenant_count", width: 90 },
                  {
                    title: "操作",
                    width: 150,
                    render: (_, user) => (
                      <Popconfirm title="确认切换用户状态？" onConfirm={() => void toggleUser(user)}>
                        <Button size="small" danger={user.status !== "disabled"}>
                          {user.status === "disabled" ? "启用" : "禁用"}
                        </Button>
                      </Popconfirm>
                    ),
                  },
                ]}
              />
            ),
          },
          {
            key: "invites",
            label: "邀请码",
            children: (
              <>
                <Space wrap style={{ marginBottom: 12 }}>
                  <Button
                    type="primary"
                    icon={<UserAddOutlined />}
                    loading={creatingResumeInvite}
                    onClick={() => void createResumeInvite()}
                  >
                    生成简历邀请码
                  </Button>
                  <Button icon={<PlusOutlined />} onClick={() => setInviteOpen(true)}>
                    自定义邀请码
                  </Button>
                </Space>
                <Table
                  rowKey="id"
                  loading={loading}
                  dataSource={invites}
                  pagination={false}
                  scroll={{ x: 760 }}
                  expandable={{
                    expandedRowRender: (invite) => (
                      <Space orientation="vertical" size={4}>
                        {invite.uses.length === 0 ? (
                          <Text type="secondary">暂无使用记录</Text>
                        ) : invite.uses.map((use) => (
                          <Text key={use.id}>{use.username} · {use.used_at ? new Date(use.used_at).toLocaleString("zh-CN") : ""}</Text>
                        ))}
                      </Space>
                    ),
                  }}
                  columns={[
                    {
                      title: "邀请码",
                      dataIndex: "code",
                      width: 260,
                      render: (_code, invite: AdminInviteCode) => (
                        <Space size={4}>
                          <Text code copyable={false} style={{ whiteSpace: "nowrap" }}>{invite.code}</Text>
                          <Tooltip title="复制邀请码">
                            <Button
                              type="text"
                              size="small"
                              icon={<CopyOutlined />}
                              aria-label={`复制邀请码 ${invite.code}`}
                              onClick={() => void copyInviteCode(invite)}
                            />
                          </Tooltip>
                        </Space>
                      ),
                    },
                    { title: "状态", dataIndex: "status", render: statusTag, width: 120 },
                    { title: "已用", dataIndex: "used_count", width: 90 },
                    {
                      title: "剩余",
                      width: 90,
                      render: (_value, invite: AdminInviteCode) => Math.max(invite.max_uses - invite.used_count, 0),
                    },
                    { title: "上限", dataIndex: "max_uses", width: 90 },
                    {
                      title: "操作",
                      width: 80,
                      render: (_value, invite: AdminInviteCode) => {
                        const isDisabled = invite.status === "disabled";
                        const actionLabel = isDisabled ? "恢复邀请码" : "停用邀请码";
                        return (
                          <Tooltip title={actionLabel}>
                            <Popconfirm
                              title={`确认${actionLabel}？`}
                              onConfirm={() => void toggleInviteStatus(invite)}
                            >
                              <Button
                                type="text"
                                size="small"
                                danger={!isDisabled}
                                icon={isDisabled ? <CheckCircleOutlined /> : <StopOutlined />}
                                aria-label={`${actionLabel} ${invite.code}`}
                              />
                            </Popconfirm>
                          </Tooltip>
                        );
                      },
                    },
                  ]}
                />
              </>
            ),
          },
        ]}
      />

      <Modal
        title={creditTenant ? `调整积分：${creditTenant.name}` : "调整积分"}
        open={Boolean(creditTenant)}
        onCancel={() => setCreditTenant(null)}
        onOk={() => void submitCreditAdjustment()}
        destroyOnHidden
      >
        <Form form={creditForm} layout="vertical" initialValues={{ bucket: "credits", operation: "grant" }}>
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message="增加或扣减只改变当前余额，不会抹平已消费记录；重置套餐会把总积分和剩余积分都设为新值。"
          />
          <Form.Item name="bucket" label="积分池" rules={[{ required: true }]}>
            <Select options={bucketOptions} />
          </Form.Item>
          <Form.Item name="operation" label="调整方式" rules={[{ required: true }]}>
            <Select options={creditOperationOptions} />
          </Form.Item>
          {creditOperation === "reset" ? (
            <Form.Item name="total" label="重置后总积分" rules={[{ required: true }]}>
              <InputNumber min={0} style={{ width: "100%" }} />
            </Form.Item>
          ) : (
            <Form.Item name="amount" label={creditOperation === "deduct" ? "扣减积分" : "增加积分"} rules={[{ required: true }]}>
              <InputNumber min={1} style={{ width: "100%" }} />
            </Form.Item>
          )}
          <Form.Item name="reason" label="调整原因">
            <Input />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="创建邀请码"
        open={inviteOpen}
        onCancel={() => setInviteOpen(false)}
        onOk={() => void submitInvite()}
        destroyOnHidden
      >
        <Form form={inviteForm} layout="vertical" initialValues={{ max_uses: 1 }}>
          <Form.Item name="code" label="邀请码" rules={[{ required: true }]}>
            <Input placeholder="例如 BETA-001" />
          </Form.Item>
          <Form.Item name="max_uses" label="可使用次数" rules={[{ required: true }]}>
            <InputNumber min={1} max={100} style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="邀请码已生成"
        open={Boolean(latestInvite)}
        onCancel={() => setLatestInvite(null)}
        footer={[
          <Button key="close" onClick={() => setLatestInvite(null)}>完成</Button>,
          <Button
            key="copy"
            type="primary"
            icon={<CopyOutlined />}
            onClick={() => latestInvite && void copyInviteCode(latestInvite)}
          >
            复制邀请码
          </Button>,
        ]}
      >
        {latestInvite ? (
          <Space orientation="vertical" size={12} style={{ width: "100%" }}>
            <Alert
              type="success"
              showIcon
              title={`可使用 ${latestInvite.max_uses} 次`}
              description="可以将同一个邀请码放到简历中；如需停止新用户注册，可随时在列表中停用。"
            />
            <Input value={latestInvite.code} readOnly />
          </Space>
        ) : null}
      </Modal>
    </div>
  );
}
