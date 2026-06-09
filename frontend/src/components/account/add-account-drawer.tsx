import { Drawer, Segmented, message } from "antd";
import { useState } from "react";

import type { PlatformAccount } from "../../types";
import { CookieImportPanel } from "./cookie-import-panel";
import { PhoneLoginPanel } from "./phone-login-panel";
import { QrLoginPanel } from "./qr-login-panel";

type AddAccountDrawerProps = {
  open: boolean;
  onClose: () => void;
  onBound: () => void;
};

type AccountPlatform = "xhs" | "huitun";
type AccountType = "pc" | "creator" | "main";
type LoginMethod = "qr" | "phone" | "cookie";

const platformOptions = [
  { label: "小红书", value: "xhs" as const },
  { label: "灰豚", value: "huitun" as const },
];

const accountTypeOptions = [
  { label: "PC", value: "pc" as const },
  { label: "Creator", value: "creator" as const },
];

const loginMethodOptions = [
  { label: "二维码", value: "qr" as const },
  { label: "手机验证码", value: "phone" as const },
  { label: "Cookie", value: "cookie" as const },
];

export function AddAccountDrawer({ open, onClose, onBound }: AddAccountDrawerProps) {
  const [platform, setPlatform] = useState<AccountPlatform>("xhs");
  const [accountType, setAccountType] = useState<AccountType>("pc");
  const [method, setMethod] = useState<LoginMethod>("qr");

  function handlePlatformChange(nextPlatform: AccountPlatform) {
    setPlatform(nextPlatform);
    setMethod("qr");
    setAccountType(nextPlatform === "huitun" ? "main" : "pc");
  }

  function handleConfirmed(account: PlatformAccount) {
    const actionText = account.action === "updated" ? "已更新到账号矩阵" : "已加入账号矩阵";
    message.success(`${account.nickname || "账号"} ${actionText}`);
    onBound();
  }

  return (
    <Drawer
      title={
        <div>
          <div style={{ fontSize: 12, color: "rgba(255,255,255,0.45)", marginBottom: 4, textTransform: "uppercase", letterSpacing: 1 }}>
            Account Matrix
          </div>
          <div style={{ fontSize: 18, fontWeight: 600, color: "rgba(255,255,255,0.88)" }}>添加小红书 / 灰豚账号</div>
        </div>
      }
      placement="right"
      width={420}
      open={open}
      onClose={onClose}
      destroyOnClose
      styles={{
        header: { background: "#1f1f1f", borderBottom: "1px solid #303030" },
        body: { background: "#141414", padding: 24 },
      }}
    >
      <div style={{ marginBottom: 20 }}>
        <Segmented
          block
          value={platform}
          options={platformOptions}
          onChange={(val) => handlePlatformChange(val as AccountPlatform)}
        />
      </div>

      {platform === "xhs" ? (
        <div style={{ marginBottom: 20 }}>
          <Segmented
            block
            value={accountType}
            options={accountTypeOptions}
            onChange={(val) => setAccountType(val as AccountType)}
          />
        </div>
      ) : null}

      <div style={{ marginBottom: 24 }}>
        <Segmented
          block
          value={method}
          options={platform === "huitun" ? loginMethodOptions.filter((option) => option.value !== "phone") : loginMethodOptions}
          onChange={(val) => setMethod(val as LoginMethod)}
        />
      </div>

      {method === "qr" ? (
        <QrLoginPanel platform={platform} accountType={platform === "huitun" ? "main" : accountType} onConfirmed={handleConfirmed} />
      ) : method === "cookie" ? (
        <CookieImportPanel platform={platform} accountType={platform === "huitun" ? "main" : accountType} onImported={handleConfirmed} />
      ) : (
        <PhoneLoginPanel accountType={accountType as "pc" | "creator"} onConfirmed={handleConfirmed} />
      )}
    </Drawer>
  );
}
