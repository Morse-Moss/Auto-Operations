import {
  ApiOutlined,
  ArrowLeftOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  LockOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import { Alert, Button, Card, Col, List, Row, Space, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { PageHeader } from "../../components/layout/app-shell";
import { fetchWechatOfficialOverview } from "../../lib/api";
import type { WechatOfficialOverview } from "../../types";

const { Text, Title } = Typography;

const fallbackOverview: WechatOfficialOverview = {
  platform_id: "wechat_official",
  stage: "foundation_ready",
  external_integration_enabled: false,
  research_required_before_integration: true,
  research_topics: [
    "GitHub 微信公众号开源系统架构调研",
    "微信官方草稿箱、素材、群发、预览 API 能力边界确认",
    "凭据保存与加密策略确认",
    "真实群发风险与 QA 流程确认",
  ],
  capabilities: [
    {
      key: "account.manage",
      label: "账号配置",
      status: "planned",
      message: "正式接入前不开放 AppID/AppSecret 配置。",
    },
    {
      key: "content.library",
      label: "图文内容库",
      status: "planned",
      message: "待调研后设计公众号图文内容模型。",
    },
    {
      key: "content.rewrite",
      label: "文章改写",
      status: "planned",
      message: "待内容模型确认后接入公众号文章改写。",
    },
    {
      key: "publish.dry_run",
      label: "发布 dry-run",
      status: "planned",
      message: "待草稿箱、素材和群发 API 能力确认后设计。",
    },
    {
      key: "publish.real_publish",
      label: "群发发布",
      status: "blocked",
      message: "高风险动作，正式 QA、dry-run 和动作级确认机制完成前保持阻断。",
    },
  ],
  blocked_actions: ["真实授权", "素材上传", "草稿同步", "预览发送", "群发发布"],
};

function statusColor(status: string): string {
  if (status === "blocked") return "red";
  if (status === "planned") return "gold";
  if (status === "available") return "green";
  return "default";
}

export function WechatOfficialDashboard() {
  const [overview, setOverview] = useState<WechatOfficialOverview>(fallbackOverview);
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    fetchWechatOfficialOverview()
      .then((payload) => {
        setOverview(payload);
        setLoadFailed(false);
      })
      .catch(() => {
        setOverview(fallbackOverview);
        setLoadFailed(true);
      });
  }, []);

  return (
    <div>
      <PageHeader
        eyebrow="WeChat Official Workspace"
        title="公众号平台"
        description="平台骨架已纳入主系统；正式接入前先调研 GitHub 开源系统和微信官方 API 能力边界。"
        action={
          <Link to="/platform-select">
            <Button icon={<ArrowLeftOutlined />}>返回平台中心</Button>
          </Link>
        }
      />

      {loadFailed ? (
        <Alert
          showIcon
          type="warning"
          style={{ marginBottom: 24 }}
          message="公众号底座状态读取失败"
          description="当前展示本地 fallback 状态。请检查后端服务；这不是微信连接失败，因为本阶段尚未接入微信外部接口。"
        />
      ) : null}

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} md={8}>
          <Card style={{ background: "#1f1f1f", borderColor: "#303030" }}>
            <Space align="start">
              <CheckCircleOutlined style={{ color: "#52c41a", fontSize: 22 }} />
              <div>
                <Title level={5} style={{ marginTop: 0 }}>平台骨架</Title>
                <Space size={4} wrap>
                  <Tag color="blue">Beta</Tag>
                  <Tag color="green">Foundation Ready</Tag>
                </Space>
                <div style={{ marginTop: 8 }}>
                  <Text type="secondary">当前阶段：{overview.stage}</Text>
                </div>
              </div>
            </Space>
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card style={{ background: "#1f1f1f", borderColor: "#303030" }}>
            <Space align="start">
              <ApiOutlined style={{ color: "#faad14", fontSize: 22 }} />
              <div>
                <Title level={5} style={{ marginTop: 0 }}>外部接入</Title>
                <Tag color="gold">Not Connected</Tag>
                <div style={{ marginTop: 8 }}>
                  <Text type="secondary">
                    external_integration_enabled = {String(overview.external_integration_enabled)}
                  </Text>
                </div>
              </div>
            </Space>
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card style={{ background: "#1f1f1f", borderColor: "#303030" }}>
            <Space align="start">
              <SafetyCertificateOutlined style={{ color: "#ff4d4f", fontSize: 22 }} />
              <div>
                <Title level={5} style={{ marginTop: 0 }}>真实动作</Title>
                <Tag color="red">Blocked</Tag>
                <div style={{ marginTop: 8 }}>
                  <Text type="secondary">授权、素材、草稿、预览、群发均未启用。</Text>
                </div>
              </div>
            </Space>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={14}>
          <Card
            title="能力清单"
            style={{ background: "#1f1f1f", borderColor: "#303030" }}
          >
            <List
              dataSource={overview.capabilities}
              renderItem={(capability) => (
                <List.Item>
                  <List.Item.Meta
                    avatar={capability.status === "blocked" ? <LockOutlined /> : <ExclamationCircleOutlined />}
                    title={
                      <Space>
                        <span>{capability.label}</span>
                        <Tag color={statusColor(capability.status)}>{capability.status}</Tag>
                      </Space>
                    }
                    description={capability.message}
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card
            title="接入前置调研"
            style={{ background: "#1f1f1f", borderColor: "#303030", marginBottom: 16 }}
          >
            <List
              dataSource={overview.research_topics}
              renderItem={(item) => (
                <List.Item>
                  <Text>{item}</Text>
                </List.Item>
              )}
            />
          </Card>
          <Card
            title="已阻断动作"
            style={{ background: "#1f1f1f", borderColor: "#303030" }}
          >
            <Space wrap>
              {overview.blocked_actions.map((action) => (
                <Tag key={action} color="red">{action}</Tag>
              ))}
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
