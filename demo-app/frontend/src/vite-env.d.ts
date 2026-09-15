/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_UVA_PUBLISHABLE_KEY?: string;
  readonly VITE_UVA_SESSION_ENDPOINT?: string;
  readonly VITE_UVA_REFRESH_ENDPOINT?: string;
  readonly VITE_UVA_AGENT_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
