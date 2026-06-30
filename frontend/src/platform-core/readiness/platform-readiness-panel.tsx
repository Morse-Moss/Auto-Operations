import { Alert, Card, Space, Tag, Typography } from "antd";

import { PlatformActionHub } from "../actions/platform-action-hub";
import type { PlatformAction } from "../actions/platform-action-types";

const { Paragraph } = Typography;

const cardStyle = { background: "#1f1f1f", borderColor: "#303030" };

export type PlatformReadinessCheck = {
  key: string;
  label: string;
  status: string;
  message?: string;
};

export type PlatformReadinessPanelProps = {
  title?: string;
  overallStatus: string;
  nextActions: string[];
  checks: PlatformReadinessCheck[];
  actions: PlatformAction[];
  compatibilityMode?: boolean;
  compatibilityMessage?: string;
  compatibilityDescription?: string;
  blockedTags?: string[];
};

function statusColor(status?: string): string {
  if (!status) return "default";
  if (["blocked", "expired", "invalid", "failed", "rejected", "missing"].includes(status)) return "red";
  if (["planned", "partial", "pending", "unknown", "analyzing"].includes(status)) return "gold";
  if (["ready", "available", "valid", "active", "succeeded", "completed", "shortlisted"].includes(status)) return "green";
  if (["draft_ready"].includes(status)) return "purple";
  return "default";
}

export function PlatformReadinessPanel({
  title = "Readiness / Diagnostics",
  overallStatus,
  nextActions,
  checks,
  actions,
  compatibilityMode = false,
  compatibilityMessage = "后端服务版本可能未重启",
  compatibilityDescription = "readiness endpoint 不可用时已启用兼容模式；页面仍可继续使用，重启根目录后端后可恢复完整诊断。",
  blockedTags = [],
}: PlatformReadinessPanelProps) {
  return (
    <Card title={title} style={cardStyle}>
      <Space direction="vertical" style={{ width: "100%" }}>
        <Alert
          showIcon
          type={overallStatus === "ready" ? "success" : "warning"}
          message={`当前状态：${overallStatus}`}
          description={nextActions.join(" / ")}
        />
        {compatibilityMode ? (
          <Alert showIcon type="warning" message={compatibilityMessage} description={compatibilityDescription} />
        ) : null}
        <PlatformActionHub actions={actions} />
        <Space wrap>
          {checks.map((check) => <Tag key={check.key} color={statusColor(check.status)}>{check.label}: {check.status}</Tag>)}
        </Space>
        {blockedTags.length ? (
          <Space wrap>
            {blockedTags.map((tag) => <Tag key={tag} color="red">{tag}</Tag>)}
          </Space>
        ) : null}
        <Paragraph type="secondary" style={{ marginBottom: 0 }}>
          下一步建议：{nextActions.join("；")}
        </Paragraph>
      </Space>
    </Card>
  );
}
