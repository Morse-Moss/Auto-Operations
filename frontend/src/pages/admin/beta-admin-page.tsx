import {
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
  Typography,
  message,
} from "antd";
import { useEffect, useState } from "react";

import {
  activateAdminTenant,
  activateAdminUser,
  adjustAdminTenantCredit,
  createAdminInviteCode,
  disableAdminUser,
  fetchAdminInviteCodes,
  fetchAdminTenants,
  fetchAdminUsers,
  suspendAdminTenant,
} from "../../lib/api";
import type { AdminInviteCode, AdminTenant, AdminUser } from "../../types";

const { Title, Text } = Typography;

const bucketOptions = [
  { label: "图片生成", value: "image_generation" },
  { label: "AI 改写", value: "ai_rewrite" },
  { label: "文本 AI", value: "text_action" },
  { label: "草稿评分", value: "draft_score" },
  { label: "分析报告", value: "analysis_report" },
];

function statusTag(status: string) {
  const color = status === "active" ? "green" : status === "suspended" || status === "disabled" ? "red" : "default";
  return <Tag color={color}>{status}</Tag>;
}

export function BetaAdminPage() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [tenants, setTenants] = useState<AdminTenant[]>([]);
  const [invites, setInvites] = useState<AdminInviteCode[]>([]);
  const [loading, setLoading] = useState(false);
  const [creditTenant, setCreditTenant] = useState<AdminTenant | null>(null);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [creditForm] = Form.useForm();
  const [inviteForm] = Form.useForm();

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
    await adjustAdminTenantCredit(creditTenant.id, {
      bucket: values.bucket,
      total: values.total,
      reason: values.reason || "",
    });
    message.success("额度已调整");
    setCreditTenant(null);
    creditForm.resetFields();
    await loadAll();
  }

  async function submitInvite() {
    const values = await inviteForm.validateFields();
    await createAdminInviteCode({ code: values.code.trim(), max_uses: values.max_uses });
    message.success("邀请码已创建");
    setInviteOpen(false);
    inviteForm.resetFields();
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
                        <Button size="small" onClick={() => setCreditTenant(tenant)}>额度</Button>
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
                <Button type="primary" onClick={() => setInviteOpen(true)} style={{ marginBottom: 12 }}>创建邀请码</Button>
                <Table
                  rowKey="id"
                  loading={loading}
                  dataSource={invites}
                  pagination={false}
                  expandable={{
                    expandedRowRender: (invite) => (
                      <Space direction="vertical" size={4}>
                        {invite.uses.length === 0 ? (
                          <Text type="secondary">暂无使用记录</Text>
                        ) : invite.uses.map((use) => (
                          <Text key={use.id}>{use.username} · {use.used_at ? new Date(use.used_at).toLocaleString("zh-CN") : ""}</Text>
                        ))}
                      </Space>
                    ),
                  }}
                  columns={[
                    { title: "邀请码", dataIndex: "code" },
                    { title: "状态", dataIndex: "status", render: statusTag, width: 120 },
                    { title: "已用", dataIndex: "used_count", width: 90 },
                    { title: "上限", dataIndex: "max_uses", width: 90 },
                  ]}
                />
              </>
            ),
          },
        ]}
      />

      <Modal
        title={creditTenant ? `调整额度：${creditTenant.name}` : "调整额度"}
        open={Boolean(creditTenant)}
        onCancel={() => setCreditTenant(null)}
        onOk={() => void submitCreditAdjustment()}
        destroyOnHidden
      >
        <Form form={creditForm} layout="vertical">
          <Form.Item name="bucket" label="额度桶" rules={[{ required: true }]}>
            <Select options={bucketOptions} />
          </Form.Item>
          <Form.Item name="total" label="总额度" rules={[{ required: true }]}>
            <InputNumber min={0} style={{ width: "100%" }} />
          </Form.Item>
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
    </div>
  );
}
