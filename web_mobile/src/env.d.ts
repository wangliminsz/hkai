/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue';
  const component: DefineComponent<{}, {}, any>;
  export default component;
}

interface ImportMetaEnv {
  readonly VITE_APP_TITLE: string;
  readonly VITE_APP_LOGO: string;
  readonly VITE_APP_FAVICON: string;
  readonly VITE_SIGN_IN_TEXT: string;
  readonly VITE_API_URL: string;
  readonly VITE_DESKTOP_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
