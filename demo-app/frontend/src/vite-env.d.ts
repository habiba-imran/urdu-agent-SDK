/// <reference types="vite/client" />

declare const __UVA_VOICE_VERSION__: string;

interface ImportMetaEnv {
  readonly VITE_UVA_PUBLISHABLE_KEY?: string;
  readonly VITE_UVA_SESSION_ENDPOINT?: string;
  readonly VITE_UVA_REFRESH_ENDPOINT?: string;
  readonly VITE_UVA_AGENT_ID?: string;
  readonly VITE_UVA_FETCH_TIMEOUT_MS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
