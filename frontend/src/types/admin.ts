import type { PlatformUser, UsageBucketKey } from "./shared";

export type AdminUser = PlatformUser & {
  tenant_count: number;
  created_at?: string | null;
};

export type AdminTenant = {
  id: number;
  name: string;
  slug: string;
  kind: string;
  status: "active" | "suspended" | string;
  member_count: number;
  created_at?: string | null;
  updated_at?: string | null;
};

export type AdminInviteCodeUse = {
  id: number;
  used_by_user_id: number;
  username: string;
  used_at?: string | null;
};

export type AdminInviteCode = {
  id: number;
  code: string;
  max_uses: number;
  used_count: number;
  status: "active" | "disabled" | string;
  created_by_user_id?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  uses: AdminInviteCodeUse[];
};

export type AdminCreditAdjustment = {
  bucket: UsageBucketKey;
  total: number;
  remaining: number;
  status: string;
};

export type AdminCreditAdjustmentPayload = {
  bucket: UsageBucketKey;
  operation: "grant" | "deduct" | "reset";
  amount?: number;
  total?: number;
  reason?: string;
};
