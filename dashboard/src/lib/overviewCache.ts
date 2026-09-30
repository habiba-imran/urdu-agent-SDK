import type { PortalOverviewSnapshot } from '@/lib/portalApi';

const STORAGE_KEY = 'uva_overview_snapshot_v1';
const MAX_AGE_MS = 15 * 60 * 1000;

type CachedOverview = {
  savedAt: number;
  data: PortalOverviewSnapshot;
};

export function readOverviewCache(): PortalOverviewSnapshot | undefined {
  if (typeof window === 'undefined') return undefined;
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return undefined;
    const parsed = JSON.parse(raw) as CachedOverview;
    if (!parsed?.data || typeof parsed.savedAt !== 'number') return undefined;
    if (Date.now() - parsed.savedAt > MAX_AGE_MS) return undefined;
    return parsed.data;
  } catch {
    return undefined;
  }
}

export function writeOverviewCache(data: PortalOverviewSnapshot): void {
  if (typeof window === 'undefined') return;
  try {
    const payload: CachedOverview = { savedAt: Date.now(), data };
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  } catch {
    /* quota / private mode — ignore */
  }
}
