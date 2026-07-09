import {
  AimOutlined,
  BarChartOutlined,
  CloudDownloadOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  KeyOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
  SendOutlined,
  SettingOutlined,
  StarOutlined,
  ThunderboltOutlined,
  VideoCameraOutlined,
} from "@ant-design/icons";
import type { MenuProps } from "antd";
import type { ReactNode } from "react";

export type PlatformSectionStatus = "available" | "partial" | "blocked" | "planned";

export type PlatformSectionConfig = {
  key: string;
  path: string;
  label: string;
  title: string;
  description: string;
  icon?: ReactNode;
  status?: PlatformSectionStatus;
  adminOnly?: boolean;
};

export const platformSectionRegistry: Record<string, PlatformSectionConfig[]> = {
  "xhs": [
    { key: "dashboard", path: "/platforms/xhs/dashboard", icon: <DashboardOutlined />, label: "小红书总览", title: "小红书总览", description: "小红书运营数据、账号状态和生产链路总览。", status: "available" },
    { key: "accounts", path: "/platforms/xhs/accounts", icon: <SafetyCertificateOutlined />, label: "小红书账号矩阵", title: "小红书账号矩阵", description: "管理 PC 与 Creator 账号、Cookie 状态、健康检查和账号作用域。", status: "available" },
    { key: "discovery", path: "/platforms/xhs/discovery", icon: <SearchOutlined />, label: "小红书笔记发现", title: "小红书笔记发现", description: "关键词搜索、URL 直达、账号笔记抓取和批量入库。", status: "available" },
    { key: "keywords", path: "/platforms/xhs/keywords", icon: <KeyOutlined />, label: "小红书关键词组", title: "小红书关键词组", description: "管理关键词组与热词候选发现。", status: "available" },
    { key: "crawler", path: "/platforms/xhs/crawler", icon: <CloudDownloadOutlined />, label: "小红书数据获取", title: "小红书数据获取", description: "获取笔记候选、人工确认入库，并保留高风险直连入口。", status: "available" },
    { key: "library", path: "/platforms/xhs/library", icon: <DatabaseOutlined />, label: "小红书内容库", title: "小红书内容库", description: "标签、筛选、批量导出和素材下载的统一资产库。", status: "available" },
    { key: "analytics", path: "/platforms/xhs/analytics", icon: <BarChartOutlined />, label: "小红书分析中心", title: "小红书分析中心", description: "围绕关键词组、笔记和评论生成有证据的分析报告。", status: "available" },
    { key: "drafts", path: "/platforms/xhs/drafts", icon: <FileTextOutlined />, label: "小红书草稿工坊", title: "小红书草稿工坊", description: "把收藏笔记转化为可编辑草稿。", status: "available" },
    { key: "image-studio", path: "/platforms/xhs/image-studio", icon: <StarOutlined />, label: "小红书图片工坊", title: "小红书图片工坊", description: "封面生成、配图变体、版式调整和发布前图片处理。", status: "available" },
    { key: "video-studio", path: "/platforms/xhs/video-studio", icon: <VideoCameraOutlined />, label: "小红书视频工坊", title: "小红书视频工坊", description: "视频内容生产和素材处理。", status: "available" },
    { key: "publish", path: "/platforms/xhs/publish", icon: <SendOutlined />, label: "小红书发布中心", title: "小红书发布中心", description: "草稿、素材上传、立即发布、定时发布和历史记录。", status: "available" },
    { key: "auto-ops", path: "/platforms/xhs/auto-ops", icon: <ThunderboltOutlined />, label: "小红书自动运营", title: "小红书自动运营", description: "关键词自动抓取、AI 改写和发布任务生产线。", status: "available" },
    { key: "benchmarks", path: "/platforms/xhs/benchmarks", icon: <AimOutlined />, label: "小红书竞品监控", title: "小红书竞品监控", description: "跟踪目标账号、品牌、关键词与内容模式。", status: "available" },
  ],
  "demo-platform": [
    { key: "library", path: "/platforms/demo-platform/library", icon: <DatabaseOutlined />, label: "Demo 内容库", title: "Demo 内容库", description: "只读 fixture，验证 Platform Core 共享内容库路径。", status: "partial" },
  ],
  "wechat-official": [
    { key: "dashboard", path: "/platforms/wechat-official/dashboard", icon: <DashboardOutlined />, label: "公众号总览", title: "公众号运营总览", description: "汇总 Redfox 配置、爆文候选、内容库和 blocked 动作状态。", status: "available" },
    { key: "accounts", path: "/platforms/wechat-official/accounts", icon: <SafetyCertificateOutlined />, label: "公众号账号矩阵", title: "公众号账号矩阵", description: "查看公众号账号接入状态；真实授权和发布动作仍保持阻断。", status: "partial" },
    { key: "discovery", path: "/platforms/wechat-official/discovery", icon: <SearchOutlined />, label: "公众号爆文发现", title: "公众号爆文发现", description: "通过关键词、公众号或文章 URL 收集爆文候选，并把确认后的候选交给内容库。", status: "available" },
    { key: "library", path: "/platforms/wechat-official/library", icon: <DatabaseOutlined />, label: "公众号内容库", title: "公众号内容库", description: "管理已入库的公众号文章，补全素材、拆解爆点并生成独立草稿。", status: "available" },
    { key: "drafts", path: "/platforms/wechat-official/drafts", icon: <FileTextOutlined />, label: "公众号草稿工坊", title: "公众号草稿工坊", description: "基于内容库素材生成和管理公众号二创草稿。", status: "available" },
    { key: "settings", path: "/platforms/wechat-official/settings", icon: <SettingOutlined />, label: "Redfox 设置", title: "Redfox 设置", description: "配置和校验 Redfox API Key；Redfox 只作为内容数据源。", status: "available", adminOnly: true },
  ],
};

export function getPlatformIdFromPath(pathname: string): string {
  const parts = pathname.split("/").filter(Boolean);
  if (parts[0] === "platforms" && parts[1]) return parts[1];
  return "xhs";
}

export function getPlatformSections(platformId: string, options?: { includeAdminOnly?: boolean }): PlatformSectionConfig[] {
  const sections = platformSectionRegistry[platformId] ?? platformSectionRegistry.xhs;
  if (options?.includeAdminOnly === false) {
    return sections.filter((section) => !section.adminOnly);
  }
  return sections;
}

export function getPlatformNavItems(platformId: string, options?: { includeAdminOnly?: boolean }): MenuProps["items"] {
  return [
    { key: "/platform-select", icon: <DashboardOutlined />, label: "平台中心" },
    ...getPlatformSections(platformId, options).map((section) => ({
      key: section.path,
      icon: section.icon,
      label: section.label,
    })),
  ];
}

export function getPlatformSection(platformId: string, sectionKey: string): PlatformSectionConfig | undefined {
  return getPlatformSections(platformId).find((section) => section.key === sectionKey);
}
