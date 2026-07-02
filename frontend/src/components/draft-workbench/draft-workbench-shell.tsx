import { useState, type ReactNode } from "react";

import { Alert, Button, Card, Col, Empty, Input, List, Row, Space, Tag, Typography } from "antd";
import { DeleteOutlined, CopyOutlined, ReloadOutlined, SaveOutlined } from "@ant-design/icons";

import type { DraftWorkbenchAdapter, DraftWorkbenchController, DraftWorkbenchDraft } from "./draft-workbench-types";

const { Paragraph, Text } = Typography;

const DEFAULT_EDITOR_LABELS = {
  draftNameLabel: "内部草稿名",
  draftNamePlaceholder: "例如：浴缸案例图替换 - 0622 A版",
  titleLabel: "发布标题",
  titlePlaceholder: "输入发布标题",
  bodyLabel: "正文",
  bodyPlaceholder: "输入草稿正文",
  tagsLabel: "标签",
  assistantTitle: "AI 助手",
  assistantDescription: "平台相关的改写、校验或辅助动作放在这里。",
};

export type DraftWorkbenchShellProps<TDraft extends DraftWorkbenchDraft> = {
  adapter: DraftWorkbenchAdapter<TDraft>;
  controller: DraftWorkbenchController<TDraft>;
  renderSourcePanel?: (draft: TDraft) => ReactNode;
  renderContextPanel?: (draft: TDraft) => ReactNode;
  renderEditorExtras?: (draft: TDraft) => ReactNode;
  renderPrimaryActions?: (draft: TDraft) => ReactNode;
  renderAssistantExtras?: (draft: TDraft) => ReactNode;
};

function formatDraftTime(value: string): string {
  return value ? value.replace("T", " ").slice(0, 16) : "";
}

export function DraftWorkbenchShell<TDraft extends DraftWorkbenchDraft>({
  adapter,
  controller,
  renderSourcePanel,
  renderContextPanel,
  renderEditorExtras,
  renderPrimaryActions,
  renderAssistantExtras,
}: DraftWorkbenchShellProps<TDraft>) {
  const [isDraftListOpen, setIsDraftListOpen] = useState(false);
  const selectedDraft = controller.selectedDraft;
  const emptyState = adapter.getEmptyState();
  const editorLabels = adapter.editorLabels ?? DEFAULT_EDITOR_LABELS;
  const canDuplicate = adapter.capabilities.canDuplicate && Boolean(controller.duplicateSelectedDraft);
  const canDelete = adapter.capabilities.canDelete && Boolean(controller.deleteSelectedDraft);
  const canDryRun = adapter.capabilities.canDryRun && Boolean(controller.dryRunSelectedDraft);
  const selectedDraftName = selectedDraft?.draft_name || selectedDraft?.title || "未选择草稿";
  const hasSourcePanel = Boolean(renderSourcePanel);

  function renderDraftList() {
    if (controller.isLoading && controller.drafts.length === 0) {
      return (
        <div style={{ padding: 24, textAlign: "center" }}>
          <Text type="secondary">正在加载草稿...</Text>
        </div>
      );
    }

    if (controller.drafts.length === 0) {
      return (
        <Empty description={emptyState.description} style={{ padding: 24 }}>
          <Space direction="vertical">
            <Text strong>{emptyState.title}</Text>
            {emptyState.actionLabel ? <Button type="primary">{emptyState.actionLabel}</Button> : null}
          </Space>
        </Empty>
      );
    }

    return (
      <List
        size="small"
        dataSource={controller.drafts}
        renderItem={(draft) => {
          const isActive = draft.id === controller.selectedDraftId;
          return (
            <List.Item
              onClick={() => {
                controller.selectDraft(draft.id);
                setIsDraftListOpen(false);
              }}
              style={{
                cursor: "pointer",
                padding: "10px 12px",
                background: isActive ? "rgba(22, 104, 220, 0.08)" : "transparent",
                borderLeft: isActive ? "2px solid #1677ff" : "2px solid transparent",
              }}
            >
              <div style={{ width: "100%", display: "flex", gap: 12, alignItems: "flex-start" }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <Text strong ellipsis style={{ display: "block" }}>
                    {draft.draft_name || draft.title || "未命名草稿"}
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
    );
  }

  return (
    <div style={{ padding: 16 }}>
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <div>
          <Text type="secondary">{adapter.pageTitle}</Text>
          <h2 style={{ margin: "4px 0 0" }}>{adapter.pageDescription}</h2>
        </div>

        {controller.error ? <Alert type="error" message={controller.error} showIcon /> : null}
        {controller.message ? <Alert type="success" message={controller.message} showIcon /> : null}

        <Card size="small" styles={{ body: { padding: 12 } }}>
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
              <Space direction="vertical" size={2} style={{ minWidth: 0 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>当前草稿</Text>
                <Text strong ellipsis style={{ maxWidth: 520 }}>{selectedDraftName}</Text>
              </Space>
              <Space wrap>
                <Text type="secondary">共 {controller.drafts.length} 个草稿</Text>
                <Button onClick={() => setIsDraftListOpen((open) => !open)}>
                  {isDraftListOpen ? "收起草稿" : "切换草稿"}
                </Button>
              </Space>
            </div>
            {isDraftListOpen ? <div>{renderDraftList()}</div> : null}
          </Space>
        </Card>

        {selectedDraft && renderContextPanel ? <div>{renderContextPanel(selectedDraft)}</div> : null}

        <Row gutter={[16, 16]} align="stretch">
          {hasSourcePanel ? (
            <Col xs={24} lg={6}>
              <Card title="来源面板">
                {!selectedDraft ? (
                  <Empty description="选择草稿后显示来源信息" />
                ) : (
                  <div>{renderSourcePanel?.(selectedDraft)}</div>
                )}
              </Card>
            </Col>
          ) : null}

          <Col xs={24} lg={hasSourcePanel ? 12 : 16}>
            <Card title="草稿编辑器">
              {!selectedDraft ? (
                <Empty description="请先选择一个草稿" />
              ) : (
                <Space direction="vertical" size={16} style={{ width: "100%" }}>
                  <div>
                    <Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
                      {editorLabels.draftNameLabel}
                    </Text>
                    <Input
                      value={controller.draftName}
                      onChange={(event) => controller.setDraftName(event.target.value)}
                      placeholder={editorLabels.draftNamePlaceholder}
                    />
                  </div>

                  <div>
                    <Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
                      {editorLabels.titleLabel}
                    </Text>
                    <Input
                      value={controller.title}
                      onChange={(event) => controller.setTitle(event.target.value)}
                      placeholder={editorLabels.titlePlaceholder}
                    />
                  </div>

                  <div>
                    <Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
                      {editorLabels.bodyLabel}
                    </Text>
                    <Input.TextArea
                      value={controller.body}
                      onChange={(event) => controller.setBody(event.target.value)}
                      placeholder={editorLabels.bodyPlaceholder}
                      rows={16}
                    />
                  </div>

                  <div>
                    <Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
                      {editorLabels.tagsLabel}
                    </Text>
                    <Space size={[4, 8]} wrap>
                      {controller.tags.map((tag) => (
                        <Tag
                          key={tag.id || tag.name}
                          closable
                          onClose={(event) => {
                            event.preventDefault();
                            controller.setTags(controller.tags.filter((currentTag) => currentTag !== tag));
                          }}
                        >
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

                  {renderPrimaryActions ? <div>{renderPrimaryActions(selectedDraft)}</div> : null}
                </Space>
              )}
            </Card>
          </Col>

          <Col xs={24} lg={hasSourcePanel ? 6 : 8}>
            <Card title={editorLabels.assistantTitle}>
              {selectedDraft ? (
                <Space direction="vertical" size={16} style={{ width: "100%" }}>
                  <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                    {editorLabels.assistantDescription}
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
