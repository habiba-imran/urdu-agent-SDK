import { getAgents, getCredentials, getSessions, getUsageSummary } from '@/lib/portalApi';
import { getVoiceCatalogue } from '@/lib/voicesApi';

/**
 * One key + fetcher per resource, shared by every page and by Sidebar's hover-prefetch.
 * SWR's cache is a single global store keyed by these strings, so two pages requesting the
 * same key (e.g. Overview and Agents both use `agents`) share one cached result and one
 * in-flight request — navigating between them never double-fetches.
 */
export const swrKeys = {
  agents: 'agents',
  credentials: 'credentials',
  sessions: 'sessions',
  usage: 'usage',
  voices: 'voices',
} as const;

export const swrFetchers = {
  agents: () => getAgents(),
  credentials: () => getCredentials(),
  sessions: () => getSessions(),
  usage: () => getUsageSummary(30),
  voices: () => getVoiceCatalogue(),
};
