import { Alert, Button, Form, Input, Space, Typography } from "antd";
import { LoginOutlined } from "@ant-design/icons";
import { useEffect, useState } from "react";

import { apiErrorMessage, confirmHuitunPasswordLogin } from "../../lib/api";
import type { PlatformAccount } from "../../types";

const { Text } = Typography;
const TENCENT_CAPTCHA_APP_ID = "190387174";
const TENCENT_CAPTCHA_SCRIPT_ID = "tencent-captcha-script";

type TencentCaptchaResult = {
  ret: number;
  ticket?: string;
  randstr?: string;
};

type TencentCaptchaCtor = new (
  appId: string,
  callback: (result: TencentCaptchaResult) => void
) => { show: () => void };

type HuitunPasswordLoginPanelProps = {
  onConfirmed: (account: PlatformAccount) => void;
};

declare global {
  interface Window {
    TencentCaptcha?: TencentCaptchaCtor;
  }
}

function loadTencentCaptcha(): Promise<TencentCaptchaCtor> {
  if (window.TencentCaptcha) {
    return Promise.resolve(window.TencentCaptcha);
  }

  return new Promise((resolve, reject) => {
    const existing = document.getElementById(TENCENT_CAPTCHA_SCRIPT_ID) as HTMLScriptElement | null;
    if (existing) {
      existing.addEventListener("load", () => {
        if (window.TencentCaptcha) resolve(window.TencentCaptcha);
        else reject(new Error("captcha unavailable"));
      }, { once: true });
      existing.addEventListener("error", () => reject(new Error("captcha load failed")), { once: true });
      return;
    }

    const script = document.createElement("script");
    script.id = TENCENT_CAPTCHA_SCRIPT_ID;
    script.src = "https://turing.captcha.qcloud.com/TCaptcha.js";
    script.async = true;
    script.onload = () => {
      if (window.TencentCaptcha) resolve(window.TencentCaptcha);
      else reject(new Error("captcha unavailable"));
    };
    script.onerror = () => reject(new Error("captcha load failed"));
    document.body.appendChild(script);
  });
}

function requestTencentCaptcha(): Promise<{ ticket: string; randStr: string }> {
  return loadTencentCaptcha().then(
    (TencentCaptcha) =>
      new Promise((resolve, reject) => {
        const captcha = new TencentCaptcha(TENCENT_CAPTCHA_APP_ID, (result) => {
          if (result.ret !== 0 || !result.ticket || !result.randstr) {
            reject(new Error("captcha cancelled"));
            return;
          }
          resolve({ ticket: result.ticket, randStr: result.randstr });
        });
        captcha.show();
      })
  );
}

export function HuitunPasswordLoginPanel({ onConfirmed }: HuitunPasswordLoginPanelProps) {
  const [mobile, setMobile] = useState("");
  const [password, setPassword] = useState("");
  const [captchaCode, setCaptchaCode] = useState("");
  const [needsSmsCode, setNeedsSmsCode] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [statusText, setStatusText] = useState("使用官方验证完成登录后，系统会保存登录态。");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadTencentCaptcha().catch(() => undefined);
  }, []);

  async function handleLogin() {
    setError(null);
    if (!mobile.trim() || !password) {
      setError("请填写手机号和密码。");
      return;
    }
    if (needsSmsCode && !captchaCode.trim()) {
      setError("请填写短信验证码。");
      return;
    }

    setIsSubmitting(true);
    try {
      setStatusText("正在打开官方验证...");
      const captcha = await requestTencentCaptcha();
      setStatusText("正在确认登录态...");
      const result = await confirmHuitunPasswordLogin({
        mobile: mobile.trim(),
        password,
        ticket: captcha.ticket,
        randStr: captcha.randStr,
        captcha: needsSmsCode ? captchaCode.trim() : undefined,
      });

      if (result.status === "verification_required") {
        setNeedsSmsCode(true);
        setStatusText(result.message || "当前设备需要短信验证。");
        return;
      }

      const account = result.account;
      if (result.status === "confirmed" && account) {
        setStatusText("登录态已保存。");
        setPassword("");
        setCaptchaCode("");
        onConfirmed(account);
        return;
      }

      setError("登录未完成，请重新验证后再试。");
      setStatusText("等待重新验证。");
    } catch (caught) {
      const fallback = caught instanceof Error && caught.message === "captcha cancelled"
        ? "验证已取消，请重新点击登录。"
        : "登录失败，请检查账号密码或重新完成验证。";
      setError(apiErrorMessage(caught, fallback));
      setStatusText("等待重新验证。");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Text style={{ color: "rgba(255,255,255,0.72)" }}>{statusText}</Text>

      <Form layout="vertical">
        <Form.Item label={<span style={{ color: "rgba(255,255,255,0.88)" }}>手机号</span>}>
          <Input
            value={mobile}
            onChange={(event) => setMobile(event.target.value)}
            autoComplete="username"
            placeholder="请输入手机号"
            style={{ background: "#1f1f1f", borderColor: "#303030", color: "rgba(255,255,255,0.88)" }}
          />
        </Form.Item>
        <Form.Item label={<span style={{ color: "rgba(255,255,255,0.88)" }}>密码</span>}>
          <Input.Password
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            placeholder="请输入密码"
            style={{ background: "#1f1f1f", borderColor: "#303030", color: "rgba(255,255,255,0.88)" }}
          />
        </Form.Item>
        {needsSmsCode ? (
          <Form.Item label={<span style={{ color: "rgba(255,255,255,0.88)" }}>短信验证码</span>}>
            <Input
              value={captchaCode}
              onChange={(event) => setCaptchaCode(event.target.value)}
              autoComplete="one-time-code"
              placeholder="请输入短信验证码"
              style={{ background: "#1f1f1f", borderColor: "#303030", color: "rgba(255,255,255,0.88)" }}
            />
          </Form.Item>
        ) : null}
      </Form>

      {error ? <Alert type="error" message={error} showIcon /> : null}

      <Button
        type="primary"
        block
        icon={<LoginOutlined />}
        onClick={() => void handleLogin()}
        loading={isSubmitting}
      >
        {isSubmitting ? "登录中..." : "登录并保存"}
      </Button>
    </Space>
  );
}
