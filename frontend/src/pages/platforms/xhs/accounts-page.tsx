import { Button, Modal, Space, Typography } from "antd";
import {
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { AddAccountDrawer } from "../../../components/account/add-account-drawer";
import { checkAccount, deleteAccount, fetchAccounts } from "../../../lib/api";
import { formatShanghaiTime } from "../../../lib/time";
import type { PlatformAccount } from "../../../types";
import { PlatformAccountsShell } from "../../../platform-core/accounts/platform-accounts-shell";
import type { PlatformAccountCardItem } from "../../../platform-core/accounts/platform-account-types";

const { Text, Title } = Typography;

function formatDate(value?: string): string {
  return formatShanghaiTime(value);
}

function profileValue(account: PlatformAccount, key: string): string | null {
  const value = account.profile?.[key];
  if (value === null || value === undefined || value === "") {
    return null;
  }
  return String(value);
}

const statusColorMap: Record<string, string> = {
  active: "green",
  healthy: "green",
  expired: "red",
  unknown: "default",
};

const statusLabelMap: Record<string, string> = {
  active: "正常",
  healthy: "正常",
  expired: "过期",
  unknown: "未知",
};

type XhsAccountCardItem = PlatformAccountCardItem & {
  borderColor: string;
  updatedAtLabel: string;
};

function accountTypeBadge(account: PlatformAccount): NonNullable<PlatformAccountCardItem["badge"]> {
  if (account.platform === "huitun") {
    return { key: "type", label: "数据账号", color: "gold" };
  }
  if (account.sub_type === "creator") {
    return { key: "type", label: "Creator", color: "purple" };
  }
  return { key: "type", label: "PC", color: "blue" };
}

function accountMetrics(account: PlatformAccount): NonNullable<PlatformAccountCardItem["metrics"]> {
  if (account.platform === "huitun") {
    return [
      { key: "type", title: "类型", value: "数据账号" },
      { key: "usage", title: "用途", value: "热词与数据获取" },
    ];
  }

  if (account.sub_type === "creator") {
    const redId = profileValue(account, "red_id");
    return [
      { key: "type", title: "类型", value: "Creator" },
      ...(redId ? [{ key: "red_id", title: "小红书号", value: redId }] : []),
    ];
  }

  return [
    { key: "type", title: "类型", value: "PC" },
    { key: "followers", title: "粉丝", value: profileValue(account, "followers") || "-" },
    { key: "following", title: "关注", value: profileValue(account, "following") || "-" },
    { key: "likes", title: "获赞", value: profileValue(account, "likes") || "-" },
  ];
}

function accountBorderColor(account: PlatformAccount): string {
  if (account.platform === "huitun") {
    return "#d48806";
  }
  if (account.sub_type === "creator") {
    return "#722ed1";
  }
  return "#1668dc";
}

type AccountActionHandlers = {
  isChecking: (accountId: number) => boolean;
  onCheck: (accountId: number) => void;
  onDelete: (account: PlatformAccount) => void;
};

function toXhsAccountCardItems(
  accounts: PlatformAccount[],
  { isChecking, onCheck, onDelete }: AccountActionHandlers,
): XhsAccountCardItem[] {
  return accounts.map((account) => {
    const checking = isChecking(account.id);
    const statusColor = statusColorMap[account.status] || "default";
    const statusLabel = statusLabelMap[account.status] || account.status;
    const borderColor = accountBorderColor(account);

    return {
      key: String(account.id),
      borderColor,
      updatedAtLabel: `更新时间：${formatDate(account.updated_at || account.created_at)}`,
      title: account.nickname || "未命名账号",
      subtitle: account.external_user_id || "external id pending",
      avatar: account.avatar_url || undefined,
      avatarText: !account.avatar_url ? (account.nickname?.slice(0, 1).toUpperCase() || "X") : undefined,
      status: { key: "status", label: statusLabel, color: statusColor },
      badge: accountTypeBadge(account),
      metrics: accountMetrics(account),
      description: account.status_message || undefined,
      actions: [
        {
          key: "check",
          label: (
            <Space size={4}>
              {checking ? <SyncOutlined spin /> : <ReloadOutlined />}
              {checking ? "检查中" : "检查"}
            </Space>
          ),
          onClick: () => onCheck(account.id),
          disabled: checking,
        },
        {
          key: "delete",
          label: (
            <Space size={4}>
              <DeleteOutlined />
              删除
            </Space>
          ),
          onClick: () => onDelete(account),
          danger: true,
        },
      ],
    };
  });
}

export function XhsAccountsPage() {
  const [searchParams] = useSearchParams();
  const defaultAccountType = searchParams.get("bind") === "creator" ? "creator" : "pc";
  const [accounts, setAccounts] = useState<PlatformAccount[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [checkingAccountIds, setCheckingAccountIds] = useState<Set<number>>(() => new Set());
  const [error, setError] = useState<string | null>(null);

  async function loadAccounts() {
    setIsLoading(true);
    setError(null);
    try {
      const loadedAccounts = await fetchAccounts();
      setAccounts(loadedAccounts);
    } catch {
      setError("账号列表加载失败。");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleCheck(accountId: number) {
    if (checkingAccountIds.has(accountId)) {
      return;
    }
    setError(null);
    setCheckingAccountIds((current) => new Set(current).add(accountId));
    try {
      const checked = await checkAccount(accountId);
      setAccounts((current) => current.map((account) => (account.id === checked.id ? checked : account)));
    } catch {
      setError("账号健康检查失败。");
    } finally {
      setCheckingAccountIds((current) => {
        const next = new Set(current);
        next.delete(accountId);
        return next;
      });
    }
  }

  async function handleDelete(account: PlatformAccount) {
    Modal.confirm({
      title: "删除账号",
      content: `删除账号「${account.nickname || account.external_user_id || account.id}」？本地保存的账号 Cookie 也会移除。`,
      okText: "确认删除",
      cancelText: "取消",
      okButtonProps: { danger: true },
      onOk: async () => {
        setError(null);
        try {
          await deleteAccount(account.id);
          setAccounts((current) => current.filter((item) => item.id !== account.id));
        } catch {
          setError("账号删除失败。");
        }
      },
    });
  }

  const accountItems = toXhsAccountCardItems(accounts, {
    isChecking: (accountId) => checkingAccountIds.has(accountId),
    onCheck: (accountId) => void handleCheck(accountId),
    onDelete: (account) => void handleDelete(account),
  });

  useEffect(() => {
    void loadAccounts();
  }, []);

  useEffect(() => {
    if (searchParams.get("bind") === "creator") {
      setDrawerOpen(true);
    }
  }, [searchParams]);

  return (
    <div style={{ padding: "0 0 32px" }}>
      <div style={{ marginBottom: 28 }}>
        <Text
          style={{
            fontSize: 11,
            textTransform: "uppercase",
            letterSpacing: 1.5,
            color: "rgba(255,255,255,0.35)",
            display: "block",
            marginBottom: 4,
          }}
        >
          XHS Accounts
        </Text>
        <Title level={3} style={{ margin: 0, color: "rgba(255,255,255,0.88)" }}>
          账号矩阵
        </Title>
        <Text style={{ color: "rgba(255,255,255,0.45)", marginTop: 4, display: "block" }}>
          管理小红书账号与数据账号、登录态、健康检查和账号作用域。
        </Text>
      </div>

      <PlatformAccountsShell
        title="已绑定账号"
        description="管理小红书账号与数据账号、登录态、健康检查和账号作用域。"
        items={accountItems}
        loading={isLoading}
        error={error}
        emptyTitle="还没有绑定小红书账号或数据账号"
        emptyDescription={(
          <Space direction="vertical" size={8}>
            <SafetyCertificateOutlined style={{ fontSize: 48, color: "rgba(255,255,255,0.25)" }} />
            <Text strong style={{ color: "rgba(255,255,255,0.65)" }}>
              还没有绑定小红书账号或数据账号
            </Text>
            <Text style={{ color: "rgba(255,255,255,0.35)", fontSize: 13 }}>
              绑定小红书 PC 账号用于搜索和抓取；绑定数据账号用于自动获取关键词候选词。
            </Text>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setDrawerOpen(true)}>
              添加账号
            </Button>
          </Space>
        )}
        toolbar={(
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadAccounts} loading={isLoading}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setDrawerOpen(true)}>
              绑定账号
            </Button>
          </Space>
        )}
        renderExtra={(item) => {
          const xhsItem = item as XhsAccountCardItem;
          return (
            <Text
              style={{
                display: "block",
                fontSize: 11,
                color: "rgba(255,255,255,0.3)",
                borderTop: `2px solid ${xhsItem.borderColor}`,
                paddingTop: 12,
              }}
            >
              {xhsItem.updatedAtLabel}
            </Text>
          );
        }}
      />

      <AddAccountDrawer
        key={defaultAccountType}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onBound={loadAccounts}
        defaultAccountType={defaultAccountType}
      />
      {/* AddAccountDrawer owns the QR/login panels; this page only opens the binding UI and never starts real login automatically. */}
    </div>
  );
}
