import { ArrowLeftOutlined } from "@ant-design/icons";
import { Alert, Button, Space } from "antd";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { PageHeader } from "../../components/layout/app-shell";

export type PlatformSectionPageProps = {
  platformLabel: string;
  title: string;
  description: string;
  safetyMessage?: string;
  safetyDescription?: string;
  action?: ReactNode;
  children: ReactNode;
};

export function PlatformSectionPage({
  platformLabel,
  title,
  description,
  safetyMessage,
  safetyDescription,
  action,
  children,
}: PlatformSectionPageProps) {
  return (
    <div>
      <PageHeader
        eyebrow={`自动化运营系统 / ${platformLabel}`}
        title={title}
        description={description}
        action={(
          <Space>
            {action}
            <Link to="/platform-select"><Button icon={<ArrowLeftOutlined />}>平台中心</Button></Link>
          </Space>
        )}
      />
      {safetyMessage ? (
        <Alert
          showIcon
          type="info"
          style={{ marginBottom: 16 }}
          message={safetyMessage}
          description={safetyDescription}
        />
      ) : null}
      {children}
    </div>
  );
}
