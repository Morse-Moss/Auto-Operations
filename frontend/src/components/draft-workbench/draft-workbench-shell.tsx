import type { ReactNode } from "react";

import { Alert, Button, Card, Col, Empty, Input, List, Row, Space, Tag, Typography } from "antd";
import { DeleteOutlined, CopyOutlined, ReloadOutlined, SaveOutlined } from "@ant-design/icons";

import type { DraftWorkbenchAdapter, DraftWorkbenchController, DraftWorkbenchDraft } from "./draft-workbench-types";

const { Paragraph, Text } = Typography;

export type DraftWorkbenchShellProps<TDraft extends DraftWorkbenchDraft> = {
  adapter: DraftWorkbenchAdapter<TDraft>;
  controller: DraftWorkbenchController<TDraft>;
  renderEditorExtras?: (draft: TDraft) => ReactNode;
  renderAssistantExtras?: (draft: TDraft) => ReactNode;
};

function formatDraftTime(value: string): string {
  return value ? value.replace("T", " ").slice(0, 16) : "";
}

export function DraftWorkbenchShell<TDraft extends DraftWorkbenchDraft>({
  adapter,
  controller,
  renderEditorExtras,
  renderAssistantExtras,
}: DraftWorkbenchShellProps<TDraft>) {
  const selectedDraft = controller.selectedDraft;
  const emptyState = adapter.getEmptyState();
  const canDuplicate = adapter.capabilities.canDuplicate && Boolean(controller.duplicateSelectedDraft);
  const canDelete = adapter.capabilities.canDelete && Boolean(controller.deleteSelectedDraft);
  const canDryRun = adapter.capabilities.canDryRun && Boolean(controller.dryRunSelectedDraft);

  return (
    <div style={{ padding: 16 }}>
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <div>
          <Text type="secondary">{adapter.pageTitle}</Text>
          <h2 style={{ margin: "4px 0 0" }}>{adapter.pageDescription}</h2>
        </div>

        {controller.error ? <Alert type="error" message={controller.error} showIcon /> : null}
        {controller.message ? <Alert type="success" message={controller.message} showIcon /> : null}

        <Row gutter={16} align="stretch">
          <Col xs={24} lg={6}>
            <Card
              title={
                <Space>
                  <Text strong>草稿列表</Text>
                  <Text type="secondary">{controller.drafts.length}</Text>
                </Space>
              }
              styles={{ body: { padding: 0 } }}
            >
              {controller.isLoading && controller.drafts.length === 0 ? (
                <div style={{ padding: 32, textAlign: "center" }}>
                  <Text type="secondary">正在加载草稿...</Text>
                </div>
              ) : controller.drafts.length === 0 ? (
                <Empty
                  description={emptyState.description}
                  style={{ padding: 32 }}
                >
                  <Space direction="vertical">
                    <Text strong>{emptyState.title}</Text>
                    {emptyState.actionLabel ? <Button type="primary">{emptyState.actionLabel}</Button> : null}
                  </Space>
                </Empty>
              ) : (
                <List
                  dataSource={controller.drafts}
                  renderItem={(draft) => {
                    const isActive = draft.id === controller.selectedDraftId;
                    return (
                      <List.Item
                        onClick={() => controller.selectDraft(draft.id)}
                        style={{
                          cursor: "pointer",
                          padding: "12px 16px",
                          background: isActive ? "rgba(22, 104, 220, 0.08)" : "transparent",
                          borderLeft: isActive ? "2px solid #1677ff" : "2px solid transparent",
                        }}
                      >
                        <div style={{ width: "100%", display: "flex", gap: 12, alignItems: "flex-start" }}>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <Text strong ellipsis style={{ display: "block" }}>
                              {draft.title || "未命名草稿"}
                            </Text>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              {adapter.getListSubtitle(draft) || formatDraftTime(draft.created_at)}
                            </Text>
                          </div>
                        </div>
                      </List.Item>
                    );
                  }}
                />
              )}
            </Card>
          </Col>

          <Col xs={24} lg={12}>
            <Card title="草稿编辑器">
              {!selectedDraft ? (
                <Empty description="请先选择一个草稿" />
              ) : (
                <Space direction="vertical" size={16} style={{ width: "100%" }}>
                  <div>
                    <Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
                      标题
                    </Text>
                    <Input
                      value={controller.title}
                      onChange={(event) => controller.setTitle(event.target.value)}
                      placeholder="输入草稿标题"
                    />
                  </div>

                  <div>
                    <Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
                      正文
                    </Text>
                    <Input.TextArea
                      value={controller.body}
                      onChange={(event) => controller.setBody(event.target.value)}
                      placeholder="输入草稿正文"
                      rows={16}
                    />
                  </div>

                  <div>
                    <Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
                      标签
                    </Text>
                    <Space size={[4, 8]} wrap>
                      {controller.tags.map((tag) => (
                        <Tag key={tag.id || tag.name} closable>
                          #{tag.name}
                        </Tag>
                      ))}
                    </Space>
                  </div>

                  {renderEditorExtras ? <div>{renderEditorExtras(selectedDraft)}</div> : null}

                  <Space wrap>
                    <Button type="primary" icon={<SaveOutlined />} onClick={() => void controller.saveSelectedDraft()} loading={controller.isLoading}>
                      保存
                    </Button>
                    {canDuplicate ? (
                      <Button icon={<CopyOutlined />} onClick={() => void controller.duplicateSelectedDraft()} loading={controller.isLoading}>
                        复制
                      </Button>
                    ) : null}
                    {canDelete ? (
                      <Button danger icon={<DeleteOutlined />} onClick={() => void controller.deleteSelectedDraft()} loading={controller.isLoading}>
                        删除
                      </Button>
                    ) : null}
                    {canDryRun ? (
                      <Button icon={<ReloadOutlined />} onClick={() => void controller.dryRunSelectedDraft({})} loading={controller.isLoading}>
                        Dry-run
                      </Button>
                    ) : null}
                  </Space>
                </Space>
              )}
            </Card>
          </Col>

          <Col xs={24} lg={6}>
            <Card title="AI 助手">
              {selectedDraft ? (
                <Space direction="vertical" size={16} style={{ width: "100%" }}>
                  <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                    平台相关的改写、校验或辅助动作放在这里。
                  </Paragraph>
                  {renderAssistantExtras ? <div>{renderAssistantExtras(selectedDraft)}</div> : null}
                </Space>
              ) : (
                <Empty description="选择草稿后显示 AI 助手" />
              )}
            </Card>
          </Col>
        </Row>
      </Space>
    </div>
  );
}
