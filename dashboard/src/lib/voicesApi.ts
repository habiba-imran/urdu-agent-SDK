const CONTROL_PLANE_URL = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL;

export type ApiVoice = {
  id: string;
  displayName: string;
  gender: 'male' | 'female' | 'unspecified' | string;
  previewUrl: string | null;
  artworkUrl: string | null;
  enabled: boolean;
};

export class VoicesApiConfigError extends Error {}

/**
 * `/v1/voices` is control_plane's public, unauthenticated catalogue endpoint (the same one
 * @awaazlabs-uva/voice's static `listVoices()` calls directly from the browser) - a different service
 * from tenant_portal_api, so it needs its own base URL, not NEXT_PUBLIC_TENANT_PORTAL_API_URL.
 */
export async function getVoiceCatalogue(): Promise<ApiVoice[]> {
  if (!CONTROL_PLANE_URL) {
    throw new VoicesApiConfigError(
      'Missing NEXT_PUBLIC_CONTROL_PLANE_URL in dashboard/.env.local',
    );
  }

  const response = await fetch(`${CONTROL_PLANE_URL.replace(/\/$/, '')}/v1/voices`, {
    cache: 'no-store',
  });

  if (!response.ok) {
    throw new Error(`Failed to load voice catalogue: ${response.status} ${response.statusText}`);
  }

  return (await response.json()) as ApiVoice[];
}
