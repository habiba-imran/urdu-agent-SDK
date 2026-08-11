import { getAgents, getCredentials, getSessions, getUsageSummary } from '@/lib/portalApi';
import { getVoiceCatalogue } from '@/lib/voicesApi';
import {
  getTelnyxConnection,
  getManagedNumbers,
  getTelephonyReadiness,
  getNumberDrift,
} from '@/lib/telephonyApi';

/**
 * One key + fetcher per resource, shared by every page and by Sidebar's hover-prefetch.
 * SWR's cache is a single global store keyed by these strings, so two pages requesting the
 * same key (e.g. Overview and Telephony both use `telephonyConnection`) share one cached result and one
 * in-flight request — navigating between them never double-fetches.
 */
export const swrKeys = {
  agents: 'agents',
  credentials: 'credentials',
  sessions: 'sessions',
  usage: 'usage',
  voices: 'voices',
  telephonyConnection: 'telephonyConnection',
  telephonyNumbers: 'telephonyNumbers',
  telephonyReadiness: 'telephonyReadiness',
  telephonyDrift: 'telephonyDrift',
} as const;

export const swrFetchers = {
  agents: () => getAgents(),
  credentials: () => getCredentials(),
  sessions: () => getSessions(),
  usage: () => getUsageSummary(),
  voices: () => getVoiceCatalogue(),
  telephonyConnection: () => getTelnyxConnection(),
  telephonyNumbers: () => getManagedNumbers(),
  telephonyReadiness: () => getTelephonyReadiness(),
  telephonyDrift: () => getNumberDrift(),
};
