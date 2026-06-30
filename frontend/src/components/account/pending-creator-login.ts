import { pollXhsLoginSession } from "../../lib/api";
import type { PlatformAccount, XhsQrLoginSession } from "../../types";

const PENDING_CREATOR_LOGIN_SESSION_KEY = "xhs_pending_creator_login_session_id";

export function rememberPendingCreatorLoginSession(session: XhsQrLoginSession): void {
  if (session.session_id) {
    window.localStorage.setItem(PENDING_CREATOR_LOGIN_SESSION_KEY, String(session.session_id));
  }
}

export function clearPendingCreatorLoginSession(sessionId?: number): void {
  const current = window.localStorage.getItem(PENDING_CREATOR_LOGIN_SESSION_KEY);
  if (!current || sessionId === undefined || current === String(sessionId)) {
    window.localStorage.removeItem(PENDING_CREATOR_LOGIN_SESSION_KEY);
  }
}

export async function recoverPendingCreatorLogin(): Promise<PlatformAccount | null> {
  const stored = window.localStorage.getItem(PENDING_CREATOR_LOGIN_SESSION_KEY);
  const sessionId = stored ? Number(stored) : null;
  if (!sessionId || !Number.isFinite(sessionId)) {
    clearPendingCreatorLoginSession();
    return null;
  }

  const polled = await pollXhsLoginSession(sessionId);
  if (polled.status === "confirmed") {
    clearPendingCreatorLoginSession(sessionId);
    return polled.account ?? polled.creator_account ?? null;
  }
  if (polled.status === "expired") {
    clearPendingCreatorLoginSession(sessionId);
  }
  return null;
}
