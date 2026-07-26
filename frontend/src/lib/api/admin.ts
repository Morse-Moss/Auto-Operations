import { http } from "./client";
import type {
  AdminCreditAdjustment,
  AdminCreditAdjustmentPayload,
  AdminInviteCode,
  AdminTenant,
  AdminUser,
  Paginated
} from "../../types";

export async function fetchAdminUsers(): Promise<Paginated<AdminUser>> {
  const response = await http.get<Paginated<AdminUser>>("/admin/users");
  return response.data;
}

export async function fetchAdminTenants(): Promise<Paginated<AdminTenant>> {
  const response = await http.get<Paginated<AdminTenant>>("/admin/tenants");
  return response.data;
}

export async function suspendAdminTenant(tenantId: number): Promise<AdminTenant> {
  const response = await http.post<AdminTenant>(`/admin/tenants/${tenantId}/suspend`);
  return response.data;
}

export async function activateAdminTenant(tenantId: number): Promise<AdminTenant> {
  const response = await http.post<AdminTenant>(`/admin/tenants/${tenantId}/activate`);
  return response.data;
}

export async function disableAdminUser(userId: number): Promise<AdminUser> {
  const response = await http.post<AdminUser>(`/admin/users/${userId}/disable`);
  return response.data;
}

export async function activateAdminUser(userId: number): Promise<AdminUser> {
  const response = await http.post<AdminUser>(`/admin/users/${userId}/activate`);
  return response.data;
}

export async function adjustAdminTenantCredit(
  tenantId: number,
  payload: AdminCreditAdjustmentPayload
): Promise<AdminCreditAdjustment> {
  const response = await http.post<AdminCreditAdjustment>(`/admin/tenants/${tenantId}/credits/adjust`, payload);
  return response.data;
}

export async function fetchAdminInviteCodes(): Promise<Paginated<AdminInviteCode>> {
  const response = await http.get<Paginated<AdminInviteCode>>("/admin/invite-codes");
  return response.data;
}

export async function createAdminInviteCode(payload: { code?: string; max_uses: number }): Promise<AdminInviteCode> {
  const response = await http.post<AdminInviteCode>("/admin/invite-codes", payload);
  return response.data;
}

export async function disableAdminInviteCode(inviteId: number): Promise<AdminInviteCode> {
  const response = await http.post<AdminInviteCode>(`/admin/invite-codes/${inviteId}/disable`);
  return response.data;
}

export async function activateAdminInviteCode(inviteId: number): Promise<AdminInviteCode> {
  const response = await http.post<AdminInviteCode>(`/admin/invite-codes/${inviteId}/activate`);
  return response.data;
}
