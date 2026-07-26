import type { PlatformAccount } from "../../../types";

export type XhsPcAccountOption = {
  value: number;
  label: string;
  disabled: boolean;
};

function xhsPcAccounts(accounts: PlatformAccount[]): PlatformAccount[] {
  return accounts.filter((account) => account.platform === "xhs" && account.sub_type === "pc");
}

export function selectReadyXhsPcAccountId(
  accounts: PlatformAccount[],
  currentAccountId: number | null,
): number | null {
  const pcAccounts = xhsPcAccounts(accounts);
  const current = pcAccounts.find((account) => account.id === currentAccountId);
  if (current?.login_ready === true) return current.id;
  return pcAccounts.find((account) => account.login_ready === true)?.id ?? null;
}

export function buildXhsPcAccountOptions(accounts: PlatformAccount[]): XhsPcAccountOption[] {
  return xhsPcAccounts(accounts).map((account) => {
    const ready = account.login_ready === true;
    return {
      value: account.id,
      label: `${account.nickname || `PC 账号 ${account.id}`} · ${ready ? "可用" : "需重新登录"}`,
      disabled: !ready,
    };
  });
}
