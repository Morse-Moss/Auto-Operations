import { Alert, Drawer, Segmented, message } from "antd";
import { useEffect, useState } from "react";

import { fetchPlatforms } from "../../lib/api";
import type { PlatformAccount } from "../../types";
import {
  accountDrawerTitleFor,
  accountTypeOptionsFor,
  getAccountAuthSchema,
  getDefaultAccountType,
  getDefaultLoginMethod,
  isUnavailableLoginMethod,
  loginMethodOptionsFor,
  mapPlatformRegistryToAccountAuthSchemas,
  platformOptionsFor,
  supportsPhoneLogin,
  type AccountAuthSchema,
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
  schemas?: readonly AccountAuthSchema[];
};

export function AddAccountDrawer({ open, onClose, onBound, defaultAccountType = "pc", schemas }: AddAccountDrawerProps) {
  const [registrySchemas, setRegistrySchemas] = useState<readonly AccountAuthSchema[]>(() => mapPlatformRegistryToAccountAuthSchemas([]));
  const availableSchemas = schemas ?? registrySchemas;
  const defaultSchema = getAccountAuthSchema("xhs", availableSchemas);
  const initialAccountType = getDefaultAccountType(defaultSchema, defaultAccountType);
  const [platform, setPlatform] = useState<AccountPlatform>(defaultSchema.platform);
  const [accountType, setAccountType] = useState<AccountType>(() => initialAccountType);
  const [method, setMethod] = useState<LoginMethod>(() => getDefaultLoginMethod(defaultSchema, undefined, initialAccountType));
  const schema = getAccountAuthSchema(platform, availableSchemas);
  const effectiveAccountType = getDefaultAccountType(schema, accountType);
  const effectiveMethod = getDefaultLoginMethod(schema, method, effectiveAccountType);
  const selectedLoginMethod = schema.loginMethods.find((option) => option.value === effectiveMethod);
  const unavailableReason = selectedLoginMethod?.description || schema.unavailableReason || "该账号绑定方式暂未开放。";
  const loginUnavailable = isUnavailableLoginMethod(schema, effectiveMethod);
  const platformOptions = platformOptionsFor(availableSchemas);
  const drawerTitle = accountDrawerTitleFor(availableSchemas);

  useEffect(() => {
    if (schemas || !open) return;
    let ignore = false;
    fetchPlatforms()
      .then((platforms) => {
        if (!ignore) {
          setRegistrySchemas(mapPlatformRegistryToAccountAuthSchemas(platforms));
        }
      })
      .catch(() => {
        if (!ignore) {
          setRegistrySchemas(mapPlatformRegistryToAccountAuthSchemas([]));
        }
      });
    return () => {
      ignore = true;
    };
  }, [open, schemas]);

  useEffect(() => {
    if (!open) return;
    const nextSchema = getAccountAuthSchema("xhs", availableSchemas);
    const nextAccountType = getDefaultAccountType(nextSchema, defaultAccountType);
    setPlatform(nextSchema.platform);
    setAccountType(nextAccountType);
    setMethod(getDefaultLoginMethod(nextSchema, undefined, nextAccountType));
  }, [availableSchemas, defaultAccountType, open]);

  function handlePlatformChange(nextPlatform: AccountPlatform) {
    const nextSchema = getAccountAuthSchema(nextPlatform, availableSchemas);
    const nextAccountType = getDefaultAccountType(nextSchema);
    setPlatform(nextSchema.platform);
    setAccountType(nextAccountType);
    setMethod(getDefaultLoginMethod(nextSchema, undefined, nextAccountType));
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

      {loginUnavailable ? (
        <Alert type="info" showIcon message="账号绑定暂未开放" description={unavailableReason} />
      ) : effectiveMethod === "qr" && (schema.platform === "xhs" || schema.platform === "huitun") ? (
        <QrLoginPanel platform={schema.platform} accountType={effectiveAccountType} onConfirmed={handleConfirmed} />
      ) : effectiveMethod === "cookie" && (schema.platform === "xhs" || schema.platform === "huitun") ? (
        <CookieImportPanel platform={schema.platform} accountType={effectiveAccountType} onImported={handleConfirmed} />
      ) : effectiveMethod === "phone" && schema.platform === "xhs" && supportsPhoneLogin(effectiveAccountType) ? (
        <PhoneLoginPanel accountType={effectiveAccountType} onConfirmed={handleConfirmed} />
      ) : null}
    </Drawer>
  );
}
