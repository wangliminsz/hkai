const env = import.meta.env as Record<string, string | undefined>;

export const SIGN_IN_TEXT: string = env.VITE_SIGN_IN_TEXT || '';
