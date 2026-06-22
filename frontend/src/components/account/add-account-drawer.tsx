import { Drawer, Segmented, message } from "antd";
import { useEffect, useState } from "react";

import type { PlatformAccount } from "../../types";
import {
  accountAuthSchemas,
  accountDrawerTitleFor,
  accountTypeOptionsFor,
  getAccountAuthSchema,
  getDefaultAccountType,
  getDefaultLoginMethod,
  loginMethodOptionsFor,
  platformOptionsFor,
  supportsPhoneLogin,
  type AccountPlatform,
  type AccountType,
  type LoginMethod,
} from "./account-auth-schema";
import { CookieImportPanel } from "./cookie-import-panel";
import { PhoneLoginPanel } from "./phone-login-panel";
import { QrLoginPanel } from "./qr-login-panel";

type AddAccountDrawerProps = {
  open: boolean;
  onClose: () => void;
  onBound: () => void;
  defaultAccountType?: "pc" | "creator";
};

const platformOptions = platformOptionsFor(accountAuthSchemas);
const drawerTitle = accountDrawerTitleFor(accountAuthSchemas);

export function AddAccountDrawer({ open, onClose, onBound, defaultAccountType = "pc" }: AddAccountDrawerProps) {
  const defaultSchema = getAccountAuthSchema("xhs");
  const [platform, setPlatform] = useState<AccountPlatform>(defaultSchema.platform);
  const [accountType, setAccountType] = useState<AccountType>(() => getDefaultAccountType(defaultSchema, defaultAccountType));
  const [method, setMethod] = useState<LoginMethod>(() => getDefaultLoginMethod(defaultSchema));
  const schema = getAccountAuthSchema(platform);
  const effectiveAccountType = getDefaultAccountType(schema, accountType);
  const effectiveMethod = getDefaultLoginMethod(schema, method);

  useEffect(() => {
    if (!open) return;
    const nextSchema = getAccountAuthSchema("xhs");
    setPlatform(nextSchema.platform);
    setAccountType(getDefaultAccountType(nextSchema, defaultAccountType));
    setMethod(getDefaultLoginMethod(nextSchema));
  }, [defaultAccountType, open]);

  function handlePlatformChange(nextPlatform: AccountPlatform) {
    const nextSchema = getAccountAuthSchema(nextPlatform);
    setPlatform(nextSchema.platform);
    setAccountType(getDefaultAccountType(nextSchema));
    setMethod(getDefaultLoginMethod(nextSchema));
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
          <div style={{ fontSize: 18, fontWeight: 600, color: "rgba(255,255,255,0.88)" }}>{drawerTitle}</div>
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

      {schema.accountTypeSelectorVisible ? (
        <div style={{ marginBottom: 20 }}>
          <Segmented
            block
            value={effectiveAccountType}
            options={accountTypeOptionsFor(schema)}
            onChange={(val) => setAccountType(val as AccountType)}
          />
        </div>
      ) : null}

      <div style={{ marginBottom: 24 }}>
        <Segmented
          block
          value={effectiveMethod}
          options={loginMethodOptionsFor(schema)}
          onChange={(val) => setMethod(val as LoginMethod)}
        />
      </div>

      {effectiveMethod === "qr" ? (
        <QrLoginPanel platform={schema.platform} accountType={effectiveAccountType} onConfirmed={handleConfirmed} />
      ) : effectiveMethod === "cookie" ? (
        <CookieImportPanel platform={schema.platform} accountType={effectiveAccountType} onImported={handleConfirmed} />
      ) : supportsPhoneLogin(effectiveAccountType) ? (
        <PhoneLoginPanel accountType={effectiveAccountType} onConfirmed={handleConfirmed} />
      ) : null}
    </Drawer>
  );
}
