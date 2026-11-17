const env = import.meta.env as Record<string, string | undefined>;

export const APP_TITLE: string = env.VITE_APP_TITLE || 'DAYBETTER';

export const APP_LOGO: string = env.VITE_APP_LOGO || '/db_trans.png';
