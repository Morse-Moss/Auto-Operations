import { ExclamationCircleOutlined } from "@ant-design/icons";
import { Alert, Collapse, Space, Tabs, Tag, Typography } from "antd";
import { useSearchParams } from "react-router-dom";

import { XhsCrawlerPage } from "./crawler-page";
import { XhsDataAcquisitionPage } from "./data-acquisition-page";
import { XhsDiscoveryPage } from "./discovery-page";
import { XhsKeywordsPage } from "./keywords-page";

const { Text, Title } = Typography;
type DataSourceView = "keywords" | "system" | "realtime";

function sourceView(searchParams: URLSearchParams): DataSourceView {
  const source = searchParams.get("source");
  return source === "keywords" || source === "realtime" ? source : "system";
}

export function XhsDataSourcesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeView = sourceView(searchParams);

  function selectView(view: string) {
    const next = new URLSearchParams(searchParams);
    next.set("source", view === "keywords" || view === "realtime" ? view : "system");
    setSearchParams(next, { replace: true });
  }

  return (
    <div>
      <div style={{ marginBottom: 12 }}>
        <Title level={4} style={{ margin: 0 }}>系统数据源</Title>
        <Text type="secondary">从关键词组开始管理计划采集；系统发现用于候选入库，小红书实时仅用于必要的即时验证。</Text>
      </div>

      <Tabs
        activeKey={activeView}
        onChange={selectView}
        items={[
          {
            key: "keywords",
            label: "关键词组",
          },
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

      {activeView === "keywords" ? (
        <XhsKeywordsPage />
      ) : activeView === "system" ? (
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
