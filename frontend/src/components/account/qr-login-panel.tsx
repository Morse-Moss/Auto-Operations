import { Alert, Button, Card, Checkbox, Space, Typography } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { useEffect, useRef, useState } from "react";

import {
  createHuitunQrLoginSession,
  createXhsCreatorQrLoginSession,
  createXhsPcQrLoginSession,
  pollHuitunLoginSession,
  pollXhsLoginSession,
} from "../../lib/api";
import type { PlatformAccount, XhsQrLoginSession } from "../../types";
import { accountLoginErrorMessage } from "./account-login-errors";
import { clearPendingCreatorLoginSession, rememberPendingCreatorLoginSession } from "./pending-creator-login";

const { Text, Link: AntLink } = Typography;

type QrLoginPanelProps = {
  platform?: "xhs" | "huitun";
  accountType: "pc" | "creator" | "main";
  onConfirmed: (account: PlatformAccount) => void;
};

type ReusableQrSession = {
  session: XhsQrLoginSession;
  expiresAt: number;
};

const reusableQrSessions = new Map<string, ReusableQrSession>();
const inFlightQrSessions = new Map<string, Promise<XhsQrLoginSession>>();

function qrSessionKey(platform: "xhs" | "huitun", accountType: "pc" | "creator" | "main", syncCreator: boolean): string {
  return `${platform}:${accountType}:${syncCreator}`;
}

async function createQrSession(
  platform: "xhs" | "huitun",
  accountType: "pc" | "creator" | "main",
  syncCreator: boolean,
  reuseExisting: boolean,
): Promise<XhsQrLoginSession> {
  const key = qrSessionKey(platform, accountType, syncCreator);
  if (reuseExisting) {
    const reusable = reusableQrSessions.get(key);
    if (reusable && reusable.expiresAt > Date.now()) {
      return reusable.session;
    }
    const inFlight = inFlightQrSessions.get(key);
    if (inFlight) {
      return inFlight;
    }
  }

  const request = platform === "huitun"
    ? createHuitunQrLoginSession()
    : accountType === "pc"
      ? createXhsPcQrLoginSession({ sync_creator: syncCreator })
      : createXhsCreatorQrLoginSession();

  if (!reuseExisting) {
    return request;
  }

  inFlightQrSessions.set(key, request);
  try {
    const session = await request;
    reusableQrSessions.set(key, { session, expiresAt: Date.now() + 1500 });
    window.setTimeout(() => {
      const current = reusableQrSessions.get(key);
      if (current?.session.session_id === session.session_id) {
        reusableQrSessions.delete(key);
      }
    }, 1500);
    return session;
  } finally {
    inFlightQrSessions.delete(key);
  }
}

export function QrLoginPanel({ platform = "xhs", accountType, onConfirmed }: QrLoginPanelProps) {
  const [session, setSession] = useState<XhsQrLoginSession | null>(null);
  const [statusText, setStatusText] = useState("准备生成二维码");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [syncCreator, setSyncCreator] = useState(false);
  const confirmedRef = useRef(false);
  const requestSequenceRef = useRef(0);

  async function startSession(reuseExisting = false) {
    const requestSequence = ++requestSequenceRef.current;
    setIsLoading(true);
    setError(null);
    setSession(null);
    confirmedRef.current = false;
    setStatusText(
      platform === "huitun"
        ? "正在生成数据账号二维码，请稍候"
        : accountType === "creator"
          ? "正在生成 Creator 二维码，请稍候"
          : "正在生成小红书 PC 二维码，请稍候"
    );
    try {
      const nextSession = await createQrSession(platform, accountType, syncCreator, reuseExisting);
      if (requestSequence !== requestSequenceRef.current) {
        return;
      }
      setSession(nextSession);
      if (platform === "xhs" && accountType === "creator") {
        rememberPendingCreatorLoginSession(nextSession);
      }
      setStatusText(
        platform === "huitun"
          ? "请使用数据账号支持的扫码方式完成登录"
          : accountType === "pc"
            ? "请使用小红书 App 扫描二维码"
            : "请使用小红书 App 扫描 Creator 二维码"
      );
    } catch (caught) {
      if (requestSequence !== requestSequenceRef.current) {
        return;
      }
      setError(accountLoginErrorMessage(caught, "二维码生成失败，请稍后重试。"));
    } finally {
      if (requestSequence === requestSequenceRef.current) {
        setIsLoading(false);
      }
    }
  }

  useEffect(() => () => {
    requestSequenceRef.current += 1;
  }, []);

  useEffect(() => {
    void startSession(true);
  }, [platform, accountType, syncCreator]);

  useEffect(() => {
    if (!session?.session_id || session.status === "confirmed" || session.status === "expired") {
      return;
    }

    const pollingSessionId = session.session_id;
    const pollingRequestSequence = requestSequenceRef.current;
    let pollingCancelled = false;
    const interval = window.setInterval(async () => {
      try {
        const polled = platform === "huitun"
          ? await pollHuitunLoginSession(pollingSessionId)
          : await pollXhsLoginSession(pollingSessionId);
        if (pollingCancelled || pollingRequestSequence !== requestSequenceRef.current) {
          return;
        }
        setSession((current) => current?.session_id === pollingSessionId
          ? {
              ...polled,
              qr_image_data_url: polled.qr_image_data_url ?? current.qr_image_data_url
            }
          : current
        );
        if (polled.status === "scanned") {
          setStatusText("已扫码，请在手机端确认登录");
        } else if (polled.status === "expired") {
          if (platform === "xhs" && accountType === "creator") {
            clearPendingCreatorLoginSession(polled.session_id);
          }
          setStatusText("二维码已过期，请刷新");
        } else if (polled.status === "confirmed" && !confirmedRef.current) {
          const confirmedAccount = polled.account ?? polled.creator_account;
          if (platform === "xhs" && accountType === "creator") {
            clearPendingCreatorLoginSession(polled.session_id);
          }
          confirmedRef.current = true;
          setStatusText(platform === "huitun" ? "数据账号绑定成功" : "账号绑定成功，已登录");
          if (confirmedAccount) {
            onConfirmed(confirmedAccount);
          }
        }
      } catch (caught) {
        if (pollingCancelled || pollingRequestSequence !== requestSequenceRef.current) {
          return;
        }
        setError(accountLoginErrorMessage(caught, "轮询登录状态失败，正在等待下一次尝试。"));
      }
    }, 2000);

    return () => {
      pollingCancelled = true;
      window.clearInterval(interval);
    };
  }, [platform, accountType, onConfirmed, session?.session_id, session?.status]);

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Card
        styles={{
          body: {
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 24,
            minHeight: 220,
            background: "#1f1f1f",
          },
        }}
        style={{ borderColor: "#303030" }}
      >
        {session?.qr_image_data_url ? (
          <img
            src={session.qr_image_data_url}
            alt={platform === "huitun" ? "数据账号登录二维码" : "小红书登录二维码"}
            style={{ width: 180, height: 180, borderRadius: 8, background: "#fff", padding: 8 }}
          />
        ) : (
          <div
            style={{
              width: 180,
              height: 180,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "#262626",
              borderRadius: 8,
              color: "rgba(255,255,255,0.3)",
              fontSize: 28,
              fontWeight: 700,
            }}
          >
            QR
          </div>
        )}
      </Card>

      <div style={{ textAlign: "center" }}>
        <Text strong style={{ display: "block", marginBottom: 4, color: "rgba(255,255,255,0.88)" }}>
          {statusText}
        </Text>
        {session?.qr_url ? (
          <AntLink href={session.qr_url} target="_blank" rel="noreferrer">
            打开二维码链接
          </AntLink>
        ) : null}
      </div>

      {platform === "xhs" && accountType === "pc" ? (
        <Checkbox
          checked={syncCreator}
          onChange={(event) => setSyncCreator(event.target.checked)}
          style={{ color: "rgba(255,255,255,0.88)" }}
        >
          登录 PC 后同步 Creator 账号
        </Checkbox>
      ) : null}

      {error ? <Alert type="error" message={error} showIcon /> : null}

      <Button
        block
        icon={<ReloadOutlined />}
        onClick={() => void startSession(false)}
        loading={isLoading}
      >
        {isLoading ? "生成中..." : "刷新二维码"}
      </Button>
    </Space>
  );
}
