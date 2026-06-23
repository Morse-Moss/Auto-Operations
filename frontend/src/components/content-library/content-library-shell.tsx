import { BookOutlined, CheckSquareOutlined, DeleteOutlined, DownloadOutlined, ReloadOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Checkbox, Col, Drawer, Empty, Input, Pagination, Popconfirm, Row, Segmented, Select, Space, Spin, Statistic, Typography } from "antd";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import type { ContentLibraryAdapter, ContentLibraryController, ContentLibraryItem } from "./content-library-types";

const { Title, Text } = Typography;

export type ContentLibraryShellProps<TItem extends ContentLibraryItem> = {
  adapter: ContentLibraryAdapter<TItem>;
  controller: ContentLibraryController<TItem>;
  toolbarExtras?: ReactNode;
};

export function ContentLibraryShell<TItem extends ContentLibraryItem>({ adapter, controller, toolbarExtras }: ContentLibraryShellProps<TItem>) {
  const emptyState = adapter.emptyState;

  return (
    <div>
      <Row justify="space-between" align="middle" style={{ marginBottom: 24 }}>
        <Col>
          <Title level={4} style={{ margin: 0 }}>{adapter.pageTitle}</Title>
          <Text type="secondary">{adapter.pageDescription}</Text>
        </Col>
        <Col>
          <Space wrap>
            {toolbarExtras}
            {adapter.renderToolbarExtras?.({ controller })}
            <Button icon={<ReloadOutlined />} onClick={() => void controller.refreshItems()} loading={controller.isLoading}>刷新</Button>
          </Space>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card size="small"><Statistic title={adapter.labels.savedCountTitle} value={controller.total} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="当前视图" value={controller.viewMode === "card" ? "卡片" : "表格"} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="已选择" value={controller.selectedItemIds.length} suffix={adapter.labels.itemCountSuffix} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="平台" value={adapter.labels.platformLabel} /></Card></Col>
      </Row>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col span={5}>
            <Input placeholder={adapter.labels.filterPlaceholder} value={controller.keywordFilter} onChange={(event) => controller.setKeywordFilter(event.target.value)} allowClear />
          </Col>
          {adapter.capabilities.canTag ? (
            <Col span={4}>
              <Select
                value={controller.selectedTagFilter || undefined}
                onChange={(value) => controller.setSelectedTagFilter(value ?? "")}
                placeholder="全部标签"
                allowClear
                style={{ width: "100%" }}
                options={controller.availableTags.map((tag) => ({ value: String(tag.id), label: tag.name }))}
              />
            </Col>
          ) : null}
          <Col span={4}>
            <Select value={controller.sortBy} onChange={controller.handleSortChange} style={{ width: "100%" }} options={adapter.sortOptions} />
          </Col>
          {adapter.capabilities.canFilterFeishuAnalysis ? (
            <>
              <Col span={4}>
                <Select
                  allowClear
                  placeholder="飞书同步状态"
                  value={controller.feishuPushStatusFilter || undefined}
                  onChange={(value) => controller.setFeishuPushStatusFilter(value ?? "")}
                  style={{ width: "100%" }}
                  options={[
                    { value: "not_synced", label: "未同步" },
                    { value: "dry_run", label: "Dry-run" },
                    { value: "synced", label: "已同步" },
                    { value: "failed", label: "同步失败" },
                  ]}
                />
              </Col>
              <Col span={4}>
                <Select
                  allowClear
                  placeholder="分析状态"
                  value={controller.analysisStatusFilter || undefined}
                  onChange={(value) => controller.setAnalysisStatusFilter(value ?? "")}
                  style={{ width: "100%" }}
                  options={["待分析", "分析中", "已完成", "废弃"].map((value) => ({ value, label: value }))}
                />
              </Col>
              <Col span={4}>
                <Select
                  allowClear
                  placeholder="内容类型"
                  value={controller.contentTypeFilter || undefined}
                  onChange={(value) => controller.setContentTypeFilter(value ?? "")}
                  style={{ width: "100%" }}
                  options={["种草", "测评", "避坑", "教程", "合集/清单", "对比", "痛点共鸣", "案例故事"].map((value) => ({ value, label: value }))}
                />
              </Col>
              <Col span={4}>
                <Select
                  allowClear
                  placeholder="复用价值"
                  value={controller.reuseValueFilter || undefined}
                  onChange={(value) => controller.setReuseValueFilter(value ?? "")}
                  style={{ width: "100%" }}
                  options={["选题参考", "标题参考", "正文结构参考", "卖点表达参考", "可直接改写", "行业观察", "竞品参考", "废弃"].map((value) => ({ value, label: value }))}
                />
              </Col>
              <Col span={5}>
                <Select
                  allowClear
                  placeholder="可复用模型"
                  value={controller.reusableModelFilter || undefined}
                  onChange={(value) => controller.setReusableModelFilter(value ?? "")}
                  style={{ width: "100%" }}
                  options={["问题驱动模型", "情绪驱动模型", "场景种草模型", "对比反差模型", "测评背书模型", "教程方法模型", "故事案例模型", "IP/热点借势模型"].map((value) => ({ value, label: value }))}
                />
              </Col>
            </>
          ) : null}
          {adapter.capabilities.canFilterAssets !== false ? (
            <Col><Checkbox checked={controller.hasAssetsFilter} onChange={(event) => controller.setHasAssetsFilter(event.target.checked)}>有素材</Checkbox></Col>
          ) : null}
          {adapter.capabilities.canFilterComments !== false ? (
            <Col><Checkbox checked={controller.hasCommentsFilter} onChange={(event) => controller.setHasCommentsFilter(event.target.checked)}>有评论</Checkbox></Col>
          ) : null}
          <Col><Segmented value={controller.viewMode} onChange={(value) => controller.setViewMode(value as "card" | "table")} options={[{ label: "卡片", value: "card" }, { label: "表格", value: "table" }]} /></Col>
          <Col><Button onClick={controller.clearFilters}>重置</Button></Col>
          <Col><Button type="primary" onClick={() => void controller.refreshItems({ page: 1 })} loading={controller.isLoading}>筛选</Button></Col>
        </Row>
      </Card>

      {controller.items.length > 0 && (
        <Card size="small" style={{ marginBottom: 16 }}>
          <Space wrap>
            <Checkbox checked={controller.items.length > 0 && controller.items.every((item) => controller.selectedItemIdSet.has(item.id))} onChange={controller.toggleVisibleSelection}>{adapter.labels.selectCurrentPage}</Checkbox>
            <Text strong>{controller.selectedItemIds.length} {adapter.labels.itemCountSuffix}已选</Text>
            {adapter.capabilities.canBatchCreateDrafts ? (
              <Button icon={<CheckSquareOutlined />} disabled={controller.isBatchWorking || !controller.selectedItemIds.length} onClick={controller.createBatchRewriteDrafts} size="small">{adapter.labels.batchCreateDrafts}</Button>
            ) : null}
            {adapter.capabilities.canExport ? (
              <>
                <Button type="primary" icon={<DownloadOutlined />} disabled={controller.isBatchWorking || !controller.selectedItemIds.length} onClick={() => void controller.exportSelectedItems("json")} size="small">{adapter.labels.exportJson}</Button>
                <Button icon={<DownloadOutlined />} disabled={controller.isBatchWorking || !controller.selectedItemIds.length} onClick={() => void controller.exportSelectedItems("csv")} size="small">{adapter.labels.exportCsv}</Button>
                {controller.latestExport ? <Button icon={<DownloadOutlined />} disabled={controller.isBatchWorking} onClick={controller.downloadLatestExport} size="small">{adapter.labels.downloadExport}</Button> : null}
              </>
            ) : null}
            {adapter.capabilities.canBatchDelete ? (
              <Popconfirm title={`确定删除选中的 ${controller.selectedItemIds.length} ${adapter.labels.itemCountSuffix}内容？`} onConfirm={controller.deleteSelectedItems}>
                <Button danger icon={<DeleteOutlined />} disabled={controller.isBatchWorking || !controller.selectedItemIds.length} size="small">{adapter.labels.batchDelete}</Button>
              </Popconfirm>
            ) : null}
            <Button disabled={!controller.selectedItemIds.length} onClick={controller.clearSelection} size="small">{adapter.labels.clearSelection}</Button>
          </Space>
          {controller.batchActionMessage ? <Alert message={controller.batchActionMessage} type="info" showIcon style={{ marginTop: 8 }} closable onClose={() => controller.setBatchActionMessage(null)} /> : null}
        </Card>
      )}

      {controller.error ? <Alert message={controller.error} type="error" showIcon style={{ marginBottom: 16 }} /> : null}

      {controller.isLoading ? (
        <Spin size="large" style={{ display: "block", textAlign: "center", margin: "48px 0" }} />
      ) : controller.items.length === 0 ? (
        <Empty description={emptyState.description}>
          {emptyState.actionPath && emptyState.actionLabel ? (
            <Link to={emptyState.actionPath}><Button type="primary" icon={<BookOutlined />}>{emptyState.actionLabel}</Button></Link>
          ) : null}
        </Empty>
      ) : controller.viewMode === "table" ? (
        adapter.renderTable({
          controller,
          selectedItemIdSet: controller.selectedItemIdSet,
          openDetail: controller.openDetail,
          toggleSelection: controller.toggleItemSelection,
          deleteItem: controller.deleteItem,
        })
      ) : (
        adapter.renderCardGrid({
          controller,
          selectedItemIdSet: controller.selectedItemIdSet,
          openDetail: controller.openDetail,
          toggleSelection: controller.toggleItemSelection,
          deleteItem: controller.deleteItem,
        })
      )}

      {controller.total > 0 && (
        <div style={{ marginTop: 16, display: "flex", justifyContent: "flex-end" }}>
          <Pagination
            current={controller.page}
            pageSize={controller.pageSize}
            total={controller.total}
            showSizeChanger
            pageSizeOptions={["20", "40", "80", "100"]}
            showTotal={(count, range) => `展示 ${range[0]}-${range[1]} / 共 ${count} 条`}
            onChange={controller.handlePageChange}
          />
        </div>
      )}

      <Drawer title={controller.selectedItem?.title || adapter.labels.detailTitleFallback} open={controller.isDetailOpen} onClose={controller.closeDetail} width={640} styles={{ body: { background: "#1a1a1a" } }}>
        {controller.selectedItem ? (
          <Spin spinning={controller.isDetailLoading}>
            {controller.detailError ? <Alert message={controller.detailError} type="warning" showIcon style={{ marginBottom: 12 }} /> : null}
            {controller.detailActionMessage ? <Alert message={controller.detailActionMessage} type="success" showIcon style={{ marginBottom: 12 }} closable onClose={() => controller.setDetailActionMessage(null)} /> : null}
            {adapter.renderDetail({ controller, item: controller.selectedItem })}
          </Spin>
        ) : null}
      </Drawer>
    </div>
  );
}
