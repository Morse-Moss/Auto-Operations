import type { PlatformAccountAuthSchema, PlatformId, PlatformMeta } from "../../types";

export type AccountPlatform = Extract<PlatformId, "xhs" | "huitun" | "wechat_official">;
export type AccountType = "pc" | "creator" | "main";
export type LoginMethod = "qr" | "phone" | "cookie" | "password" | "none";

export type AccountAuthOption<T extends string> = {
  label: string;
  value: T;
  disabled?: boolean;
  description?: string;
};

export type AccountAuthSchema = {
  platform: AccountPlatform;
  label: string;
  drawerTitle: string;
  defaultAccountType: AccountType;
  accountTypes: readonly AccountAuthOption<AccountType>[];
  loginMethods: readonly AccountAuthOption<LoginMethod>[];
  accountTypeSelectorVisible: boolean;
  unavailableReason?: string;
};

const xhsAccountTypes = [
  { label: "PC", value: "pc" },
  { label: "Creator", value: "creator" },
] as const satisfies readonly AccountAuthOption<AccountType>[];

const huitunAccountTypes = [
  { label: "主账号", value: "main" },
] as const satisfies readonly AccountAuthOption<AccountType>[];

const wechatOfficialAccountTypes = [
  { label: "公众号", value: "main", disabled: true, description: "账号绑定未开放" },
] as const satisfies readonly AccountAuthOption<AccountType>[];

const xhsLoginMethods = [
  { label: "二维码", value: "qr" },
  { label: "手机验证码", value: "phone" },
] as const satisfies readonly AccountAuthOption<LoginMethod>[];

const huitunLoginMethods = [
  { label: "账号密码", value: "password" },
  { label: "二维码", value: "qr" },
  { label: "Cookie", value: "cookie" },
] as const satisfies readonly AccountAuthOption<LoginMethod>[];

const wechatOfficialLoginMethods = [
  { label: "暂未开放", value: "none", disabled: true, description: "公众号真实授权仍保持阻断，不能绑定账号。" },
] as const satisfies readonly AccountAuthOption<LoginMethod>[];

export const accountAuthSchemas = [
  {
    platform: "xhs",
    label: "小红书",
    drawerTitle: "添加小红书账号",
    defaultAccountType: "pc",
    accountTypes: xhsAccountTypes,
    loginMethods: xhsLoginMethods,
    accountTypeSelectorVisible: true,
  },
  {
    platform: "huitun",
    label: "数据账号",
    drawerTitle: "添加数据账号",
    defaultAccountType: "main",
    accountTypes: huitunAccountTypes,
    loginMethods: huitunLoginMethods,
    accountTypeSelectorVisible: false,
  },
  {
    platform: "wechat_official",
    label: "公众号",
    drawerTitle: "添加公众号账号",
    defaultAccountType: "main",
    accountTypes: wechatOfficialAccountTypes,
    loginMethods: wechatOfficialLoginMethods,
    accountTypeSelectorVisible: false,
    unavailableReason: "公众号账号绑定未开放；真实授权、发布和外部动作仍保持阻断。",
  },
] as const satisfies readonly AccountAuthSchema[];

const userFallbackSchemas: readonly AccountAuthSchema[] = accountAuthSchemas.filter((schema) => schema.platform === "xhs");
const adminFallbackSchemas: readonly AccountAuthSchema[] = accountAuthSchemas.filter((schema) => schema.platform !== "wechat_official");

const supportedPlatforms = new Set<AccountPlatform>(["xhs", "huitun", "wechat_official"]);
const supportedAccountTypes = new Set<AccountType>(["pc", "creator", "main"]);
const blockedStatuses = new Set(["blocked", "planned", "unavailable"]);

function isAccountPlatform(value: PlatformId): value is AccountPlatform {
  return supportedPlatforms.has(value as AccountPlatform);
}

function normalizeAccountType(schema: PlatformAccountAuthSchema): AccountType {
  const requested = schema.sub_type ?? schema.account_kind ?? "main";
  return supportedAccountTypes.has(requested as AccountType) ? (requested as AccountType) : "main";
}

function normalizeLoginMethod(authMode: string): LoginMethod {
  if (authMode === "qr_login") return "qr";
  if (authMode === "phone") return "phone";
  if (authMode === "cookie") return "cookie";
  return "none";
}

function accountTypeLabel(value: AccountType): string {
  if (value === "pc") return "PC";
  if (value === "creator") return "Creator";
  return "主账号";
}

function isBlocked(schema: PlatformAccountAuthSchema): boolean {
  return blockedStatuses.has(schema.status) || schema.auth_mode === "none";
}

function addUniqueOption<T extends string>(options: AccountAuthOption<T>[], option: AccountAuthOption<T>) {
  const existing = options.find((item) => item.value === option.value);
  if (existing) {
    existing.disabled = existing.disabled || option.disabled;
    existing.description = existing.description || option.description;
    return;
  }
  options.push(option);
}

function mapPlatformAuthSchema(platform: PlatformMeta): AccountAuthSchema | null {
  if (!platform.enabled || !isAccountPlatform(platform.id) || !platform.account_auth_schemas?.length) {
    return null;
  }

  const fallback = accountAuthSchemas.find((schema) => schema.platform === platform.id);
  const accountTypes: AccountAuthOption<AccountType>[] = [];
  const loginMethods: AccountAuthOption<LoginMethod>[] = [];

  for (const registrySchema of platform.account_auth_schemas) {
    const accountType = normalizeAccountType(registrySchema);
    const loginMethod = normalizeLoginMethod(registrySchema.auth_mode);
    if (platform.id === "xhs" && loginMethod === "cookie") {
      continue;
    }
    const disabled = isBlocked(registrySchema);
    const description = registrySchema.notes || (disabled ? "该账号绑定方式暂未开放。" : undefined);

    addUniqueOption(accountTypes, {
      label: accountTypeLabel(accountType),
      value: accountType,
      disabled,
      description,
    });
    addUniqueOption(loginMethods, {
      label: registrySchema.label,
      value: loginMethod,
      disabled,
      description,
    });
  }

  if (fallback && platform.id !== "wechat_official") {
    for (const option of fallback.accountTypes) {
      addUniqueOption(accountTypes, { ...option });
    }
    for (const option of fallback.loginMethods) {
      addUniqueOption(loginMethods, { ...option });
    }
  }

  if (!accountTypes.length || !loginMethods.length) {
    return null;
  }

  const firstEnabledAccountType = accountTypes.find((option) => !option.disabled) ?? accountTypes[0];
  const blockedLogin = loginMethods.find((option) => option.value === "none" || option.disabled);
  const unavailableReason = blockedLogin?.description;

  return {
    platform: platform.id,
    label: platform.name_cn,
    drawerTitle: `添加${platform.name_cn}账号`,
    defaultAccountType: firstEnabledAccountType.value,
    accountTypes,
    loginMethods,
    accountTypeSelectorVisible: fallback?.accountTypeSelectorVisible ?? accountTypes.length > 1,
    unavailableReason,
  };
}

export function mapPlatformRegistryToAccountAuthSchemas(platforms: readonly PlatformMeta[], includePrivateDataAccount = false): AccountAuthSchema[] {
  const fallbackSchemas = includePrivateDataAccount ? adminFallbackSchemas : userFallbackSchemas;
  const mapped = platforms.map(mapPlatformAuthSchema).filter((schema): schema is AccountAuthSchema => Boolean(schema));
  const visibleMapped = includePrivateDataAccount ? mapped : mapped.filter((schema) => schema.platform !== "huitun");
  if (!mapped.length) {
    return [...fallbackSchemas];
  }
  const mappedPlatforms = new Set(visibleMapped.map((schema) => schema.platform));
  return [...visibleMapped, ...fallbackSchemas.filter((schema) => !mappedPlatforms.has(schema.platform))];
}

export function getAccountAuthSchema(
  platform: AccountPlatform,
  schemas: readonly AccountAuthSchema[] = userFallbackSchemas,
): AccountAuthSchema {
  return schemas.find((schema) => schema.platform === platform) ?? schemas[0] ?? userFallbackSchemas[0];
}

export function getDefaultAccountType(schema: AccountAuthSchema, requested?: AccountType): AccountType {
  if (requested && schema.accountTypes.some((option) => option.value === requested && !option.disabled)) {
    return requested;
  }
  return schema.accountTypes.find((option) => option.value === schema.defaultAccountType && !option.disabled)?.value ?? schema.defaultAccountType;
}

export function getDefaultLoginMethod(schema: AccountAuthSchema, requested?: LoginMethod, accountType?: AccountType): LoginMethod {
  if (requested && schema.loginMethods.some((option) => option.value === requested && !option.disabled)) {
    return requested;
  }
  if (schema.platform === "xhs" && accountType === "creator") {
    const qrLogin = schema.loginMethods.find((option) => option.value === "qr" && !option.disabled);
    if (qrLogin) {
      return qrLogin.value;
    }
  }
  return schema.loginMethods.find((option) => !option.disabled)?.value ?? schema.loginMethods[0]?.value ?? "qr";
}

export function accountTypeOptionsFor(schema: AccountAuthSchema): AccountAuthOption<AccountType>[] {
  return [...schema.accountTypes];
}

export function loginMethodOptionsFor(schema: AccountAuthSchema): AccountAuthOption<LoginMethod>[] {
  return [...schema.loginMethods];
}

export function platformOptionsFor(schemas: readonly AccountAuthSchema[] = userFallbackSchemas): AccountAuthOption<AccountPlatform>[] {
  return schemas.map((schema) => ({ label: schema.label, value: schema.platform }));
}

export function accountDrawerTitleFor(schemas: readonly AccountAuthSchema[] = userFallbackSchemas): string {
  const labelText = schemas.map((schema) => schema.label).join(" / ");
  return labelText.endsWith("账号") ? `添加${labelText}` : `添加${labelText}账号`;
}

export function supportsPhoneLogin(accountType: AccountType): accountType is "pc" | "creator" {
  return accountType === "pc" || accountType === "creator";
}

export function isUnavailableLoginMethod(schema: AccountAuthSchema, method: LoginMethod): boolean {
  const option = schema.loginMethods.find((item) => item.value === method);
  return method === "none" || Boolean(option?.disabled);
}
