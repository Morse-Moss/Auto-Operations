export type PlatformActionStatus = "available" | "partial" | "blocked" | "planned";
export type PlatformActionRisk = "low" | "medium" | "high";

export type PlatformAction = {
  key: string;
  label: string;
  description?: string;
  path?: string;
  status?: PlatformActionStatus;
  risk?: PlatformActionRisk;
};
