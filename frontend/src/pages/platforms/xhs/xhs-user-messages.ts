export const CREATOR_LOGIN_REQUIRED_MESSAGE = "当前 Creator 账号未登录或登录态已失效，请先在账号矩阵中登录/更新 Creator 账号后再发布。";

export function publishErrorMessage(detail?: string | null): string {
  const message = detail?.trim();
  if (!message) {
    return "发布失败，请确认 Creator 账号和素材状态。";
  }

  const normalized = message.toLowerCase();
  if (
    normalized.includes("account has no cookies") ||
    normalized.includes("no cookies") ||
    normalized.includes("missing cookies")
  ) {
    return CREATOR_LOGIN_REQUIRED_MESSAGE;
  }

  return message;
}

export function accountLoginStatusLabel(status?: string | null): string {
  if (status === "active" || status === "healthy") return "已登录";
  if (status === "expired") return "登录已过期";
  if (status === "unknown" || !status) return "未确认登录状态";
  return status;
}
