import { LockOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import { useEffect, useMemo, useState } from "react";

import { useAuth } from "../../hooks/use-auth";
import { fetchWechatOfficialRedfoxConfig } from "../../lib/api";
import { PlatformAccountsShell } from "../../platform-core/accounts/platform-accounts-shell";
import type { PlatformAccountCardItem } from "../../platform-core/accounts/platform-account-types";
import { PlatformSectionPage } from "../../platform-core/shell/platform-section-page";
import type { WechatOfficialRedfoxConfig } from "../../types";

export function WechatOfficialAccountsPage() {
  const auth = useAuth();
  const isAdmin = auth.user?.role === "admin";
  const [redfoxConfigured, setRedfoxConfigured] = useState(false);
  const [redfoxConfig, setRedfoxConfig] = useState<WechatOfficialRedfoxConfig | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function loadRedfoxConfig() {
      setIsLoading(true);
      setError(null);
      if (!isAdmin) {
        setRedfoxConfigured(false);
        setRedfoxConfig(null);
        setIsLoading(false);
        return;
      }
      try {
        const response = await fetchWechatOfficialRedfoxConfig();
        if (!isMounted) return;
        setRedfoxConfigured(response.configured);
        setRedfoxConfig(response.config);
      } catch {
        if (!isMounted) return;
        setRedfoxConfigured(false);
        setRedfoxConfig(null);
        setError("Redfox 配置读取失败，账号矩阵仅展示本地安全边界。");
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    void loadRedfoxConfig();

    return () => {
      isMounted = false;
    };
  }, [isAdmin]);

  const accountItems = useMemo<PlatformAccountCardItem[]>(() => {
    const redfoxStatus: NonNullable<PlatformAccountCardItem["status"]> = error
      ? { key: "failed", label: "failed", color: "red" }
      : redfoxConfigured
        ? { key: "configured", label: "configured", color: "green" }
        : { key: "missing", label: "missing", color: "gold" };

    const redfoxDescription = error
      ? "无法读取本地 Redfox 配置；请前往设置页检查。"
      : redfoxConfigured
        ? `已接入 ${redfoxConfig?.name || "Redfox"}，仅作为公众号内容数据源。`
        : "尚未配置 Redfox；可在设置页配置本地数据源。";

    return [
      {
        key: "redfox-source",
        title: "Redfox 数据源",
        subtitle: "公众号爆文与候选内容来源",
        avatarText: <SafetyCertificateOutlined />,
        status: redfoxStatus,
        description: redfoxDescription,
        tags: [
          { key: "local-config", label: "仅读取本地配置", color: "blue" },
          { key: "not-provider", label: "不调用真实外部供应商", color: "default" },
        ],
        actions: [
          {
            key: "settings",
            label: "前往设置",
            href: "/platforms/wechat-official/settings",
            type: "primary",
          },
        ],
      },
      {
        key: "official-account-auth",
        title: "公众号授权",
        subtitle: "真实授权入口",
        avatarText: <LockOutlined />,
        status: { key: "blocked", label: "blocked", color: "red" },
        description: "真实公众号授权仍保持阻断；当前页面不启动扫码、授权或登录动作。",
        tags: [
          { key: "real-auth-blocked", label: "真实公众号授权仍保持阻断", color: "red" },
          { key: "display-only", label: "只展示接入状态", color: "default" },
        ],
      },
      {
        key: "publish-safety-boundary",
        title: "公众号发布能力",
        subtitle: "安全边界",
        avatarText: <LockOutlined />,
        status: { key: "blocked", label: "blocked", color: "red" },
        description: "素材上传、预览发送、群发发布均保持 blocked，没有可执行入口。",
        tags: [
          { key: "material-upload", label: "素材上传 blocked", color: "red" },
          { key: "preview-send", label: "预览发送 blocked", color: "red" },
          { key: "mass-publish", label: "群发发布 blocked", color: "red" },
        ],
      },
    ];
  }, [error, redfoxConfig?.name, redfoxConfigured]);

  return (
    <PlatformSectionPage
      platformLabel="微信公众号"
      title="公众号账号矩阵"
      description="查看公众号账号接入状态；真实授权和发布动作仍保持阻断。"
      safetyMessage="真实公众号授权仍保持阻断"
      safetyDescription="当前账号矩阵只展示接入状态和安全边界；真实授权、素材上传、草稿同步、预览发送、群发发布没有可执行入口。"
    >
      <PlatformAccountsShell
        title="公众号账号矩阵"
        description="查看 Redfox 数据源、公众号授权和发布能力安全边界。"
        items={accountItems}
        loading={isLoading}
        error={error}
      />
    </PlatformSectionPage>
  );
}
