import {
  getAgents,
  getCredentials,
  getOverview,
  getSessions,
  getUsageSummary,
  getProviderCapabilities,
  getMembers,
} from '@/lib/portalApi';
import { getVoiceCatalogue } from '@/lib/voicesApi';
import { getManagedNumbers } from '@/lib/telephonyApi';

/**
 * One key + fetcher per resource, shared by every page and by ConsoleNav hover-prefetch.
 * SWR's cache is a single global store keyed by these strings, so two pages requesting the
 * same key share one cached result and one in-flight request.
 */
export const swrKeys = {
  overview: 'overview',
  agents: 'agents',
  credentials: 'credentials',
  sessions: 'sessions',
  usage: 'usage',
  voices: 'voices',
  providerCapabilities: 'providerCapabilities',
  telephonyNumbers: 'telephonyNumbers',
  members: 'members',
} as const;

export const swrFetchers = {
  overview: () => getOverview(),
  agents: () => getAgents(),
  credentials: () => getCredentials(),
  sessions: () => getSessions(50),
  usage: () => getUsageSummary(),
  voices: () => getVoiceCatalogue(),
  providerCapabilities: () => getProviderCapabilities(),
  telephonyNumbers: () => getManagedNumbers(),
  members: () => getMembers(),
};
