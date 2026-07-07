import assert from "node:assert/strict";

import {
  accountDrawerTitleFor,
  accountTypeOptionsFor,
  getAccountAuthSchema,
  getDefaultAccountType,
  getDefaultLoginMethod,
  loginMethodOptionsFor,
  mapPlatformRegistryToAccountAuthSchemas,
  platformOptionsFor,
} from "../src/components/account/account-auth-schema.ts";
import type { PlatformMeta } from "../src/types/index.ts";

const registryPlatforms: PlatformMeta[] = [
  {
    id: "xhs",
    name_cn: "小红书",
    name_en: "Xiaohongshu",
    enabled: true,
    status: "enabled",
    release_stage: "enabled",
    region: "cn",
    platform_type: "hybrid",
    default_route: "/platforms/xhs/dashboard",
    adapter_key: "xhs",
    risk_level: "high",
    auth_modes: ["cookie", "qr_login"],
    capabilities: [],
    accent_color: "#ff2442",
    icon: "xhs",
    account_auth_schemas: [
      {
        key: "xhs-pc-cookie",
        label: "小红书 PC Cookie 导入",
        auth_mode: "cookie",
        account_kind: "pc",
        status: "available",
        requires_secret: true,
        requires_user_action: true,
        notes: "沿用现有账号矩阵 Cookie 导入路径。",
      },
      {
        key: "xhs-qr-login",
        label: "小红书扫码登录",
        auth_mode: "qr_login",
        account_kind: "pc",
        status: "partial",
        requires_secret: false,
        requires_user_action: true,
        notes: "沿用现有扫码登录路径。",
      },
      {
        key: "xhs-creator-cookie",
        label: "小红书 Creator Cookie 导入",
        auth_mode: "cookie",
        sub_type: "creator",
        status: "available",
        requires_secret: true,
        requires_user_action: true,
        notes: "沿用现有 Creator Cookie 导入路径。",
      },
      {
        key: "xhs-phone-login",
        label: "小红书手机验证码",
        auth_mode: "phone",
        sub_type: "creator",
        status: "available",
        requires_secret: false,
        requires_user_action: true,
        notes: "沿用现有手机验证码路径。",
      },
    ],
  },
  {
    id: "wechat_official",
    name_cn: "公众号",
    name_en: "WeChat Official Account",
    enabled: true,
    status: "beta",
    release_stage: "beta",
    region: "cn",
    platform_type: "content",
    default_route: "/platforms/wechat-official/library",
    adapter_key: "wechat_official",
    risk_level: "medium",
    auth_modes: ["none"],
    capabilities: [],
    accent_color: "#07c160",
    icon: "wechat",
    account_auth_schemas: [
      {
        key: "wechat-official-account-binding",
        label: "公众号账号绑定",
        auth_mode: "none",
        account_kind: "main",
        status: "blocked",
        requires_secret: false,
        requires_user_action: false,
        notes: "真实授权和发布动作仍保持阻断。",
      },
    ],
  },
];

const schemas = mapPlatformRegistryToAccountAuthSchemas(registryPlatforms);
assert.equal(schemas.length, 2);
assert.equal(schemas[0].platform, "xhs");
assert.deepEqual(accountTypeOptionsFor(schemas[0]).map((option) => option.value), ["pc", "creator"]);
assert.deepEqual(loginMethodOptionsFor(schemas[0]).map((option) => option.value), ["cookie", "qr", "phone"]);
assert.equal(getDefaultAccountType(schemas[0]), "pc");
assert.equal(getDefaultLoginMethod(schemas[0]), "cookie");
assert.equal(getDefaultLoginMethod(schemas[0], "phone"), "phone");
assert.equal(schemas[1].platform, "wechat_official");
assert.equal(schemas[1].loginMethods[0].value, "none");
assert.equal(schemas[1].loginMethods[0].disabled, true);
assert.match(schemas[1].loginMethods[0].description || "", /阻断|blocked|不可用|未开放/);
assert.equal(accountDrawerTitleFor(schemas), "添加小红书 / 公众号账号");
assert.deepEqual(platformOptionsFor(schemas).map((option) => option.value), ["xhs", "wechat_official"]);

const adminSchemas = mapPlatformRegistryToAccountAuthSchemas(registryPlatforms, true);
assert.equal(accountDrawerTitleFor(adminSchemas), "添加小红书 / 公众号 / 数据账号");
assert.deepEqual(platformOptionsFor(adminSchemas).map((option) => option.value), ["xhs", "wechat_official", "huitun"]);

const fallback = getAccountAuthSchema("xhs");
assert.deepEqual(accountTypeOptionsFor(fallback).map((option) => option.value), ["pc", "creator"]);
assert.deepEqual(loginMethodOptionsFor(fallback).map((option) => option.value), ["qr", "phone", "cookie"]);
assert.equal(getDefaultLoginMethod(fallback, "phone"), "phone");

const emptyRegistryFallback = mapPlatformRegistryToAccountAuthSchemas([]);
assert.deepEqual(platformOptionsFor(emptyRegistryFallback).map((option) => option.value), ["xhs"]);

const adminEmptyRegistryFallback = mapPlatformRegistryToAccountAuthSchemas([], true);
assert.deepEqual(platformOptionsFor(adminEmptyRegistryFallback).map((option) => option.value), ["xhs", "huitun"]);

const registryWithoutSchemasFallback = mapPlatformRegistryToAccountAuthSchemas([
  {
    ...registryPlatforms[0],
    account_auth_schemas: [],
  },
]);
assert.deepEqual(platformOptionsFor(registryWithoutSchemasFallback).map((option) => option.value), ["xhs"]);

const wechatSchema = schemas[1];
assert.equal(getDefaultLoginMethod(wechatSchema), "none");
assert.equal(loginMethodOptionsFor(wechatSchema).some((option) => option.value === "qr" || option.value === "phone" || option.value === "cookie"), false);

const blockedDuplicateRegistry = mapPlatformRegistryToAccountAuthSchemas([
  {
    ...registryPlatforms[0],
    account_auth_schemas: [
      {
        key: "xhs-pc-cookie-disabled",
        label: "小红书 PC Cookie 导入",
        auth_mode: "cookie",
        account_kind: "pc",
        status: "blocked",
        notes: "临时阻断。",
      },
    ],
  },
]);
assert.equal(loginMethodOptionsFor(blockedDuplicateRegistry[0]).find((option) => option.value === "cookie")?.disabled, true);

console.log("account-auth-schema tests passed");
