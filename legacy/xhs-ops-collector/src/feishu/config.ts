import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

export interface FeishuConfig {
  appId: string;
  appSecret: string;
  tableId: string;
  bitableAppToken?: string;
  wikiNodeToken?: string;
  viewId?: string;
  bitableUrl?: string;
}

export interface FeishuConfigEnv {
  FEISHU_APP_ID?: string;
  FEISHU_APP_SECRET?: string;
  FEISHU_BITABLE_APP_TOKEN?: string;
  FEISHU_WIKI_NODE_TOKEN?: string;
  FEISHU_TABLE_ID?: string;
  FEISHU_VIEW_ID?: string;
  FEISHU_BITABLE_URL?: string;
}

interface FeishuConfigLoadOptions {
  localEnvPaths?: string[];
}

function parseEnvFile(content: string): FeishuConfigEnv {
  const parsed: Record<string, string> = {};

  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (line === '' || line.startsWith('#')) {
      continue;
    }

    const separatorIndex = line.indexOf('=');
    if (separatorIndex < 1) {
      continue;
    }

    const key = line.slice(0, separatorIndex).trim();
    let value = line.slice(separatorIndex + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    parsed[key] = value;
  }

  return parsed as FeishuConfigEnv;
}

function loadLocalEnv(paths: string[]): FeishuConfigEnv {
  return paths.reduce<FeishuConfigEnv>((merged, filePath) => {
    const resolvedPath = resolve(filePath);
    if (!existsSync(resolvedPath)) {
      return merged;
    }
    return { ...merged, ...parseEnvFile(readFileSync(resolvedPath, 'utf8')) };
  }, {});
}

function optionalEnv(env: FeishuConfigEnv, key: keyof FeishuConfigEnv): string | undefined {
  const value = env[key]?.trim();
  return value === undefined || value === '' ? undefined : value;
}

function requiredEnv(env: FeishuConfigEnv, key: keyof FeishuConfigEnv): string {
  const value = optionalEnv(env, key);
  if (value === undefined) {
    throw new Error(`Missing required Feishu environment variable: ${key}`);
  }
  return value;
}

function extractUrlValue(url: string | undefined, pattern: RegExp): string | undefined {
  if (url === undefined) {
    return undefined;
  }
  return pattern.exec(url)?.[1];
}

function normalizeEnv(env: FeishuConfigEnv): FeishuConfigEnv {
  const bitableUrl = optionalEnv(env, 'FEISHU_BITABLE_URL');
  return {
    ...env,
    FEISHU_BITABLE_APP_TOKEN: optionalEnv(env, 'FEISHU_BITABLE_APP_TOKEN') ?? extractUrlValue(bitableUrl, /\/base\/([^/?#]+)/),
    FEISHU_WIKI_NODE_TOKEN: optionalEnv(env, 'FEISHU_WIKI_NODE_TOKEN') ?? extractUrlValue(bitableUrl, /\/wiki\/([^/?#]+)/),
    FEISHU_TABLE_ID: optionalEnv(env, 'FEISHU_TABLE_ID') ?? extractUrlValue(bitableUrl, /[?&]table=([^&#]+)/),
    FEISHU_VIEW_ID: optionalEnv(env, 'FEISHU_VIEW_ID') ?? extractUrlValue(bitableUrl, /[?&]view=([^&#]+)/),
  };
}

export function loadFeishuConfig(env: FeishuConfigEnv = process.env, options: FeishuConfigLoadOptions = {}): FeishuConfig {
  const shouldLoadLocalEnv = env === process.env || options.localEnvPaths !== undefined;
  const localEnv = shouldLoadLocalEnv ? loadLocalEnv(options.localEnvPaths ?? ['.env.local', '.env']) : {};
  const mergedEnv = normalizeEnv({ ...localEnv, ...env });
  const bitableAppToken = optionalEnv(mergedEnv, 'FEISHU_BITABLE_APP_TOKEN');
  const wikiNodeToken = optionalEnv(mergedEnv, 'FEISHU_WIKI_NODE_TOKEN');

  if (bitableAppToken === undefined && wikiNodeToken === undefined) {
    throw new Error('Missing required Feishu environment variable: FEISHU_BITABLE_APP_TOKEN or FEISHU_WIKI_NODE_TOKEN');
  }

  return {
    appId: requiredEnv(mergedEnv, 'FEISHU_APP_ID'),
    appSecret: requiredEnv(mergedEnv, 'FEISHU_APP_SECRET'),
    tableId: requiredEnv(mergedEnv, 'FEISHU_TABLE_ID'),
    bitableAppToken,
    wikiNodeToken,
    viewId: optionalEnv(mergedEnv, 'FEISHU_VIEW_ID'),
    bitableUrl: optionalEnv(mergedEnv, 'FEISHU_BITABLE_URL'),
  };
}
