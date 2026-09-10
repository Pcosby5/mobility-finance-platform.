/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** API origin, e.g. https://mobility-finance-platform.onrender.com. Empty = same origin (dev proxy). */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
