import { useCallback, useEffect, useState } from "react";

import { fetchUsageBalance } from "../lib/api";
import type { UsageBalance, UsageBucketKey } from "../types";

type UsageBalanceState = {
  balance: UsageBalance | null;
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  bucketRemaining: (bucket: UsageBucketKey) => number | null;
  bucketLabel: (bucket: UsageBucketKey) => string;
};

const BUCKET_LABELS: Record<string, string> = {
  credits: "积分",
};

export function usageBucketLabel(bucket: UsageBucketKey): string {
  return BUCKET_LABELS[bucket] ?? bucket;
}

export function useUsageBalance(): UsageBalanceState {
  const [balance, setBalance] = useState<UsageBalance | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const next = await fetchUsageBalance();
      setBalance(next);
    } catch {
      setError("积分余额加载失败");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const bucketRemaining = useCallback(
    (bucket: UsageBucketKey) => balance?.buckets?.[bucket]?.remaining ?? null,
    [balance]
  );

  return {
    balance,
    isLoading,
    error,
    refresh,
    bucketRemaining,
    bucketLabel: usageBucketLabel,
  };
}
