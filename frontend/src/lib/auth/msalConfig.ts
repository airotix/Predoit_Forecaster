import { Configuration, LogLevel } from '@azure/msal-browser';

export const AUTH_ENABLED =
  process.env.NEXT_PUBLIC_AUTH_ENABLED === 'true';

export const msalConfig: Configuration = {
  auth: {
    clientId: process.env.NEXT_PUBLIC_AZURE_CLIENT_ID || '',
    authority: `https://login.microsoftonline.com/${process.env.NEXT_PUBLIC_AZURE_TENANT_ID || 'common'}`,
    redirectUri: typeof window !== 'undefined' ? window.location.origin : 'http://localhost:3000',
  },
  cache: {
    cacheLocation: 'sessionStorage',
    storeAuthStateInCookie: true,
  },
  system: {
    loggerOptions: {
      logLevel: LogLevel.Warning,
    },
  },
};

export const loginRequest = {
  scopes: [
    process.env.NEXT_PUBLIC_AZURE_API_SCOPE ||
      `api://${process.env.NEXT_PUBLIC_AZURE_CLIENT_ID}/access_as_user`,
  ],
};

// owner and admin share the top privilege level; worker is view-only (lowest).
export type PreduitRole = 'worker' | 'manager' | 'admin' | 'owner';

export const ROLE_RANK: Record<PreduitRole, number> = {
  worker: 1,
  manager: 2,
  admin: 3,
  owner: 3,
};

const ENTRA_ROLE_MAP: Record<string, PreduitRole> = {
  'Preduit.Owner': 'owner',
  'Preduit.Admin': 'admin',
  'Preduit.Manager': 'manager',
  'Preduit.Worker': 'worker',
  // Legacy app-role name kept for migration from the 3-role model.
  'Preduit.User': 'worker',
};

export function mapEntraRoles(roles: string[] | undefined): PreduitRole {
  if (!roles?.length) {
    return AUTH_ENABLED ? 'worker' : 'admin';
  }
  let best: PreduitRole = 'worker';
  for (const raw of roles) {
    const mapped = ENTRA_ROLE_MAP[raw];
    if (mapped && ROLE_RANK[mapped] > ROLE_RANK[best]) {
      best = mapped;
    }
  }
  return best;
}

export const USER_ROUTES = ['/dashboard', '/products', '/projection', '/settings'];
export const MANAGER_ROUTES = [
  '/purchase-orders',
  '/catalogue',
  '/scope',
  '/allocation',
  '/setup',
  '/customers',
  '/budget',
  '/recommendations',
  '/validation',
];

export function routeMinRole(pathname: string): PreduitRole | null {
  if (pathname === '/login' || pathname === '/') return null;
  if (USER_ROUTES.some((r) => pathname.startsWith(r))) return 'worker';
  if (MANAGER_ROUTES.some((r) => pathname.startsWith(r))) return 'manager';
  return 'worker';
}

export function roleMeetsRequired(role: PreduitRole, required: PreduitRole): boolean {
  return ROLE_RANK[role] >= ROLE_RANK[required];
}

export const ROLE_COOKIE = 'preduit_role';
export const SESSION_COOKIE = 'preduit_session';

export function setAuthCookies(role: PreduitRole) {
  document.cookie = `${SESSION_COOKIE}=1; path=/; SameSite=Lax`;
  document.cookie = `${ROLE_COOKIE}=${role}; path=/; SameSite=Lax`;
}

export function clearAuthCookies() {
  document.cookie = `${SESSION_COOKIE}=; path=/; max-age=0`;
  document.cookie = `${ROLE_COOKIE}=; path=/; max-age=0`;
}
