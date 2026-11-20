const TOKEN_KEY = 'mhk_token';
const USER_KEY = 'mhk_user';
const LANG_KEY = 'mhk_lang';

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export const storage = {
  getToken(): string {
    return read(TOKEN_KEY) || '';
  },
  setToken(token: string) {
    window.localStorage.setItem(TOKEN_KEY, token || '');
  },
  getUser(): any {
    try {
      const raw = read(USER_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  },
  setUser(user: any) {
    if (!user) {
      window.localStorage.removeItem(USER_KEY);
      return;
    }
    window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  getLang(): string {
    return read(LANG_KEY) || 'zh-tw';
  },
  setLang(lang: string) {
    window.localStorage.setItem(LANG_KEY, lang);
  },
  clearAuth() {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(USER_KEY);
  },
};
