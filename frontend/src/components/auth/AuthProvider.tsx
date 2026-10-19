'use client';

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import {
  AccountInfo,
  EventType,
  InteractionRequiredAuthError,
  PublicClientApplication,
} from '@azure/msal-browser';
import { MsalProvider, useMsal } from '@azure/msal-react';
import {
  AUTH_ENABLED,
  PreduitRole,
  clearAuthCookies,
  loginRequest,
  mapEntraRoles,
  msalConfig,
  setAuthCookies,
} from '@/lib/auth/msalConfig';
import {
  loginWithPassword as apiLogin,
  signupWithPassword as apiSignup,
  AuthUser,
} from '@/lib/api/auth';
import { setTokenProvider } from '@/lib/api/tokenProvider';

type AuthMethod = 'password' | 'sso' | 'dev' | null;

interface AuthContextValue {
  isAuthenticated: boolean;
  isLoading: boolean;
  account: AccountInfo | null;
  user: { email: string; name: string } | null;
  role: PreduitRole;
  method: AuthMethod;
  ssoEnabled: boolean;
  login: () => Promise<void>;
  loginWithPassword: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, name: string) => Promise<void>;
  logout: () => Promise<void>;
  getAccessToken: () => Promise<string | null>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const TOKEN_KEY = 'preduit_token';
const USER_KEY = 'preduit_user';

interface LocalSession {
  token: string;
  user: AuthUser;
}

function readLocalSession(): LocalSession | null {
  if (typeof window === 'undefined') return null;
  try {
    const token = window.sessionStorage.getItem(TOKEN_KEY);
    const rawUser = window.sessionStorage.getItem(USER_KEY);
    if (!token || !rawUser) return null;
    return { token, user: JSON.parse(rawUser) as AuthUser };
  } catch {
    return null;
  }
}

function writeLocalSession(session: LocalSession) {
  window.sessionStorage.setItem(TOKEN_KEY, session.token);
  window.sessionStorage.setItem(USER_KEY, JSON.stringify(session.user));
  setAuthCookies(session.user.role);
}

function eraseLocalSession() {
  if (typeof window !== 'undefined') {
    window.sessionStorage.removeItem(TOKEN_KEY);
    window.sessionStorage.removeItem(USER_KEY);
  }
  clearAuthCookies();
}

let msalInstance: PublicClientApplication | null = null;

function getMsalInstance() {
  if (!msalInstance && typeof window !== 'undefined') {
    msalInstance = new PublicClientApplication(msalConfig);
  }
  return msalInstance;
}

interface MsalBits {
  instance: ReturnType<typeof useMsal>['instance'];
  accounts: AccountInfo[];
  inProgress: string;
}

/**
 * Shared auth state. `msal` is provided only when Azure SSO is enabled and we
 * are rendered inside an <MsalProvider>. Local (email/password) sessions always
 * take precedence over SSO, and in dev mode a synthetic user is used.
 */
function useProvideAuth(msal: MsalBits | null): AuthContextValue {
  const [localSession, setLocalSession] = useState<LocalSession | null>(() =>
    readLocalSession()
  );
  const [ssoRole, setSsoRole] = useState<PreduitRole>('worker');
  const [msalReady, setMsalReady] = useState<boolean>(!msal);

  const devRole = (process.env.NEXT_PUBLIC_AUTH_DEV_ROLE as PreduitRole) || 'admin';
  const ssoAccount = msal?.accounts[0] ?? null;

  // ── SSO: initialise MSAL and keep the role in sync ──
  useEffect(() => {
    if (!msal) return;
    msal.instance
      .initialize()
      .then(() => setMsalReady(true))
      .catch(() => setMsalReady(true));
  }, [msal]);

  const syncSsoRole = useCallback(
    async (acct: AccountInfo | null) => {
      if (!msal || !acct) {
        setSsoRole('worker');
        return;
      }
      try {
        const result = await msal.instance.acquireTokenSilent({
          ...loginRequest,
          account: acct,
        });
        const roles = (result.idTokenClaims as { roles?: string[] })?.roles;
        const mapped = mapEntraRoles(roles);
        setSsoRole(mapped);
        setAuthCookies(mapped);
      } catch {
        const mapped = mapEntraRoles(undefined);
        setSsoRole(mapped);
        setAuthCookies(mapped);
      }
    },
    [msal]
  );

  useEffect(() => {
    if (msal && msalReady && !localSession) syncSsoRole(ssoAccount);
  }, [msal, msalReady, ssoAccount, syncSsoRole, localSession]);

  useEffect(() => {
    if (!msal) return;
    const cbId = msal.instance.addEventCallback((event) => {
      if (event.eventType === EventType.LOGIN_SUCCESS && event.payload) {
        syncSsoRole(event.payload as AccountInfo);
      }
    });
    return () => {
      if (cbId) msal.instance.removeEventCallback(cbId);
    };
  }, [msal, syncSsoRole]);

  // ── Token provider used by the API client ──
  const getAccessToken = useCallback(async (): Promise<string | null> => {
    if (localSession) return localSession.token;
    if (msal && ssoAccount) {
      try {
        const result = await msal.instance.acquireTokenSilent({
          ...loginRequest,
          account: ssoAccount,
        });
        return result.accessToken;
      } catch (err) {
        if (err instanceof InteractionRequiredAuthError) {
          await msal.instance.acquireTokenRedirect({ ...loginRequest, account: ssoAccount });
        }
        return null;
      }
    }
    return null;
  }, [localSession, msal, ssoAccount]);

  useEffect(() => {
    setTokenProvider(getAccessToken);
  }, [getAccessToken]);

  // ── Actions ──
  const login = useCallback(async () => {
    if (msal) await msal.instance.loginRedirect(loginRequest);
  }, [msal]);

  const loginWithPassword = useCallback(async (email: string, password: string) => {
    const session = await apiLogin(email, password);
    writeLocalSession({ token: session.token, user: session.user });
    setLocalSession({ token: session.token, user: session.user });
  }, []);

  const signup = useCallback(async (email: string, password: string, name: string) => {
    const session = await apiSignup(email, password, name);
    writeLocalSession({ token: session.token, user: session.user });
    setLocalSession({ token: session.token, user: session.user });
  }, []);

  const logout = useCallback(async () => {
    eraseLocalSession();
    setLocalSession(null);
    if (msal && ssoAccount) {
      await msal.instance.logoutRedirect({ account: ssoAccount });
    }
  }, [msal, ssoAccount]);

  // ── Derived state ──
  const value = useMemo<AuthContextValue>(() => {
    let role: PreduitRole;
    let method: AuthMethod;
    let isAuthenticated: boolean;
    let user: { email: string; name: string } | null = null;

    if (localSession) {
      role = localSession.user.role;
      method = 'password';
      isAuthenticated = true;
      user = { email: localSession.user.email, name: localSession.user.name };
    } else if (!AUTH_ENABLED) {
      // Dev mode: synthetic user, always authenticated.
      role = devRole;
      method = 'dev';
      isAuthenticated = true;
    } else if (ssoAccount) {
      role = ssoRole;
      method = 'sso';
      isAuthenticated = true;
      user = { email: ssoAccount.username, name: ssoAccount.name || ssoAccount.username };
    } else {
      role = 'worker';
      method = null;
      isAuthenticated = false;
    }

    const isLoading = AUTH_ENABLED && !!msal && !msalReady;

    return {
      isAuthenticated,
      isLoading,
      account: ssoAccount,
      user,
      role,
      method,
      ssoEnabled: AUTH_ENABLED && !!msal,
      login,
      loginWithPassword,
      signup,
      logout,
      getAccessToken,
    };
  }, [
    localSession,
    devRole,
    ssoAccount,
    ssoRole,
    msal,
    msalReady,
    login,
    loginWithPassword,
    signup,
    logout,
    getAccessToken,
  ]);

  return value;
}

function MsalScopedProvider({ children }: { children: React.ReactNode }) {
  const { instance, accounts, inProgress } = useMsal();
  const value = useProvideAuth({ instance, accounts, inProgress });
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

function PlainProvider({ children }: { children: React.ReactNode }) {
  const value = useProvideAuth(null);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const instance = AUTH_ENABLED ? getMsalInstance() : null;
  if (instance) {
    return (
      <MsalProvider instance={instance}>
        <MsalScopedProvider>{children}</MsalScopedProvider>
      </MsalProvider>
    );
  }
  return <PlainProvider>{children}</PlainProvider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return ctx;
}
