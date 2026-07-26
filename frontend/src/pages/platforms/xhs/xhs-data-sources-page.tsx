import { ExclamationCircleOutlined, KeyOutlined } from "@ant-design/icons";
import { Alert, Button, Col, Collapse, Row, Space, Tabs, Tag, Typography } from "antd";
import { Link, useSearchParams } from "react-router-dom";

import { XhsCrawlerPage } from "./crawler-page";
import { XhsDataAcquisitionPage } from "./data-acquisition-page";
import { XhsDiscoveryPage } from "./discovery-page";

const { Text, Title } = Typography;
type DataSourceView = "system" | "realtime";

function sourceView(searchParams: URLSearchParams): DataSourceView {
  return searchParams.get("source") === "realtime" ? "realtime" : "system";
}

export function XhsDataSourcesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeView = sourceView(searchParams);

  function selectView(view: string) {
    const next = new URLSearchParams(searchParams);
    next.set("source", view === "realtime" ? "realtime" : "system");
    setSearchParams(next, { replace: true });
  }

  return (
    <div>
      <Row justify="space-between" align="middle" gutter={[16, 16]} style={{ marginBottom: 12 }}>
        <Col>
          <Title level={4} style={{ margin: 0 }}>系统数据源</Title>
          <Text type="secondary">统一获取候选笔记；优先使用系统发现，需要即时验证时再使用小红书实时。</Text>
        </Col>
        {activeView === "system" ? (
          <Col>
            <Link to="/platforms/xhs/keywords">
              <Button icon={<KeyOutlined />}>管理关键词组</Button>
            </Link>
          </Col>
        ) : null}
      </Row>

      <Tabs
        activeKey={activeView}
        onChange={selectView}
        items={[
          {
            key: "system",
            label: <Space size={6}>系统发现<Tag color="success">推荐</Tag></Space>,
          },
          {
            key: "realtime",
            label: <Space size={6}>小红书实时<Tag color="error">有风险</Tag></Space>,
          },
        ]}
        style={{ marginBottom: 16 }}
      />

      {activeView === "system" ? (
        <XhsDataAcquisitionPage embedded showDirectXhsSection={false} />
      ) : (
        <>
          <Alert
            type="warning"
            showIcon
            icon={<ExclamationCircleOutlined />}
            title="小红书实时依赖账号登录态，存在账号风险"
            description={(
              <ul style={{ margin: "8px 0 0", paddingInlineStart: 20 }}>
                <li>实时搜索、URL 直查和详情获取都由当前小红书 PC 账号发起。</li>
                <li>连续或批量操作可能触发限流、验证码、登录失效或账号封禁。</li>
                <li>历史上已出现账号封禁；建议只在明确需要时低频、少量使用。</li>
              </ul>
            )}
            style={{ marginBottom: 20 }}
          />
          <XhsDiscoveryPage />
          <Collapse
            style={{ marginTop: 20 }}
            items={[
              {
                key: "advanced-realtime-crawl",
                label: (
                  <Space>
                    <ExclamationCircleOutlined />
                    <Text strong>高级批量采集</Text>
                    <Tag color="error">高风险</Tag>
                  </Space>
                ),
                children: <XhsCrawlerPage visibleSource="xhs" />,
              },
            ]}
          />
        </>
      )}
    </div>
  );
}
