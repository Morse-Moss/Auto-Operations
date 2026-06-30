import { Alert, Avatar, Button, Card, Col, Empty, Row, Space, Spin, Statistic, Tag, Typography } from "antd";
import type { ReactNode } from "react";

import type { PlatformAccountCardItem } from "./platform-account-types";

const { Paragraph, Text, Title } = Typography;

export type PlatformAccountsShellProps = {
  title: ReactNode;
  description?: ReactNode;
  items: PlatformAccountCardItem[];
  loading?: boolean;
  error?: ReactNode;
  emptyTitle?: ReactNode;
  emptyDescription?: ReactNode;
  toolbar?: ReactNode;
  renderExtra?: (item: PlatformAccountCardItem) => ReactNode;
};

function renderTag(tag: NonNullable<PlatformAccountCardItem["status"]>) {
  return <Tag color={tag.color}>{tag.label}</Tag>;
}

export function PlatformAccountsShell({
  title,
  description,
  items,
  loading = false,
  error,
  emptyTitle = "No items",
  emptyDescription,
  toolbar,
  renderExtra,
}: PlatformAccountsShellProps) {
  const hasItems = items.length > 0;

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Space align="start" style={{ justifyContent: "space-between", width: "100%" }}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>{title}</Title>
          {description ? <Paragraph type="secondary" style={{ marginBottom: 0 }}>{description}</Paragraph> : null}
        </div>
        {toolbar ? <div>{toolbar}</div> : null}
      </Space>

      {error ? <Alert showIcon type="error" message={error} /> : null}

      <Spin spinning={loading}>
        {hasItems ? (
          <Row gutter={[16, 16]}>
            {items.map((item) => (
              <Col key={item.key} xs={24} md={12} xl={8}>
                <Card
                  title={(
                    <Space align="center">
                      <Avatar src={item.avatar}>{item.avatarText}</Avatar>
                      <Space direction="vertical" size={0}>
                        <Text strong>{item.title}</Text>
                        {item.subtitle ? <Text type="secondary">{item.subtitle}</Text> : null}
                      </Space>
                    </Space>
                  )}
                  extra={(
                    <Space size={4} wrap>
                      {item.status ? renderTag(item.status) : null}
                      {item.badge ? renderTag(item.badge) : null}
                    </Space>
                  )}
                >
                  <Space direction="vertical" size="middle" style={{ width: "100%" }}>
                    {item.metrics?.length ? (
                      <Row gutter={[12, 12]}>
                        {item.metrics.map((metric) => (
                          <Col key={metric.key} span={8}>
                            <Statistic
                              title={metric.title}
                              value={metric.value}
                              prefix={metric.prefix}
                              suffix={metric.suffix}
                            />
                          </Col>
                        ))}
                      </Row>
                    ) : null}

                    {item.description ? <Paragraph style={{ marginBottom: 0 }}>{item.description}</Paragraph> : null}

                    {item.tags?.length ? (
                      <Space wrap>{item.tags.map((tag) => <Tag key={tag.key} color={tag.color}>{tag.label}</Tag>)}</Space>
                    ) : null}

                    {renderExtra ? renderExtra(item) : null}

                    {item.actions?.length ? (
                      <Space wrap>
                        {item.actions.map((action) => (
                          <Button
                            key={action.key}
                            href={action.href}
                            onClick={action.onClick}
                            disabled={action.disabled}
                            danger={action.danger}
                            type={action.type ?? "default"}
                          >
                            {action.label}
                          </Button>
                        ))}
                      </Space>
                    ) : null}
                  </Space>
                </Card>
              </Col>
            ))}
          </Row>
        ) : (
          <Empty
            description={
              emptyDescription ? (
                <Space direction="vertical" size={0}>
                  <Text>{emptyTitle}</Text>
                  <Text type="secondary">{emptyDescription}</Text>
                </Space>
              ) : (
                emptyTitle
              )
            }
          />
        )}
      </Spin>
    </Space>
  );
}
