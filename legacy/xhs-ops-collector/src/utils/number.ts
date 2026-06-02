export function parseHuitunNumber(value: string | null | undefined): number | null {
  if (value == null) return null;

  const normalized = value.trim().replace(/,/g, '');
  if (!normalized || normalized === '--' || normalized === '暂无') return null;

  const tenThousandMatch = normalized.match(/^(-?\d+(?:\.\d+)?)(w|万)$/i);
  if (tenThousandMatch) {
    return Math.round(Number(tenThousandMatch[1]) * 10000);
  }

  const numeric = Number(normalized);
  return Number.isFinite(numeric) ? numeric : null;
}
