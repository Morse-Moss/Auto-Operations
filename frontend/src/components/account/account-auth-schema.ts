export type AccountPlatform = "xhs" | "huitun";
export type AccountType = "pc" | "creator" | "main";
export type LoginMethod = "qr" | "phone" | "cookie";

export type AccountAuthOption<T extends string> = {
  label: string;
  value: T;
};

export type AccountAuthSchema = {
  platform: AccountPlatform;
  label: string;
  drawerTitle: string;
  defaultAccountType: AccountType;
  accountTypes: readonly AccountAuthOption<AccountType>[];
  loginMethods: readonly AccountAuthOption<LoginMethod>[];
  accountTypeSelectorVisible: boolean;
};

const xhsAccountTypes = [
  { label: "PC", value: "pc" },
  { label: "Creator", value: "creator" },
] as const satisfies readonly AccountAuthOption<AccountType>[];

const huitunAccountTypes = [
  { label: "主账号", value: "main" },
] as const satisfies readonly AccountAuthOption<AccountType>[];

const xhsLoginMethods = [
  { label: "二维码", value: "qr" },
  { label: "手机验证码", value: "phone" },
  { label: "Cookie", value: "cookie" },
] as const satisfies readonly AccountAuthOption<LoginMethod>[];

const huitunLoginMethods = [
  { label: "二维码", value: "qr" },
  { label: "Cookie", value: "cookie" },
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
    label: "灰豚",
    drawerTitle: "添加灰豚账号",
    defaultAccountType: "main",
    accountTypes: huitunAccountTypes,
    loginMethods: huitunLoginMethods,
    accountTypeSelectorVisible: false,
  },
] as const satisfies readonly AccountAuthSchema[];

export function getAccountAuthSchema(platform: AccountPlatform): AccountAuthSchema {
  return accountAuthSchemas.find((schema) => schema.platform === platform) ?? accountAuthSchemas[0];
}

export function getDefaultAccountType(schema: AccountAuthSchema, requested?: AccountType): AccountType {
  if (requested && schema.accountTypes.some((option) => option.value === requested)) {
    return requested;
  }
  return schema.defaultAccountType;
}

export function getDefaultLoginMethod(schema: AccountAuthSchema, requested?: LoginMethod): LoginMethod {
  if (requested && schema.loginMethods.some((option) => option.value === requested)) {
    return requested;
  }
  return schema.loginMethods[0]?.value ?? "qr";
}

export function accountTypeOptionsFor(schema: AccountAuthSchema): AccountAuthOption<AccountType>[] {
  return [...schema.accountTypes];
}

export function loginMethodOptionsFor(schema: AccountAuthSchema): AccountAuthOption<LoginMethod>[] {
  return [...schema.loginMethods];
}

export function platformOptionsFor(schemas: readonly AccountAuthSchema[] = accountAuthSchemas): AccountAuthOption<AccountPlatform>[] {
  return schemas.map((schema) => ({ label: schema.label, value: schema.platform }));
}

export function accountDrawerTitleFor(schemas: readonly AccountAuthSchema[] = accountAuthSchemas): string {
  return `添加${schemas.map((schema) => schema.label).join(" / ")}账号`;
}

export function supportsPhoneLogin(accountType: AccountType): accountType is "pc" | "creator" {
  return accountType === "pc" || accountType === "creator";
}
