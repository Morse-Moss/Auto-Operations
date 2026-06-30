import { Button, Space, Tag, Typography } from "antd";
import { Link } from "react-router-dom";

import type { PlatformAction } from "./platform-action-types";

const { Paragraph, Text } = Typography;

function actionTagColor(status?: PlatformAction["status"]): string {
  if (status === "blocked") return "red";
  if (status === "planned" || status === "partial") return "gold";
  return "blue";
}

export type PlatformActionHubProps = {
  title?: string;
  actions: PlatformAction[];
};

export function PlatformActionHub({ title = "推荐下一步", actions }: PlatformActionHubProps) {
  if (!actions.length) return null;

  return (
    <div>
      <Paragraph strong style={{ marginBottom: 8 }}>{title}</Paragraph>
      <Space wrap>
        {actions.map((action) => {
          const isBlocked = action.status === "blocked" || action.status === "planned";
          const button = (
            <Button type="primary" disabled={isBlocked || !action.path} title={action.description}>
              {action.label}
            </Button>
          );
          return (
            <Space key={action.key} size={4}>
              {action.path && !isBlocked ? <Link to={action.path}>{button}</Link> : button}
              {action.status && action.status !== "available" ? <Tag color={actionTagColor(action.status)}>{action.status}</Tag> : null}
              {action.risk ? <Text type="secondary">{action.risk}</Text> : null}
            </Space>
          );
        })}
      </Space>
    </div>
  );
}
