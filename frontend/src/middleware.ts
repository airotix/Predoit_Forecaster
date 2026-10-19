import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

const AUTH_ENABLED = process.env.NEXT_PUBLIC_AUTH_ENABLED === 'true';
const SESSION_COOKIE = 'preduit_session';
const ROLE_COOKIE = 'preduit_role';

const USER_ROUTES = ['/dashboard', '/products', '/projection', '/settings'];
const MANAGER_ROUTES = [
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

function roleRank(role: string) {
  if (role === 'owner' || role === 'admin') return 3;
  if (role === 'manager') return 2;
  return 1; // worker (view-only) and any unknown role
}

function minRoleForPath(pathname: string): number {
  if (MANAGER_ROUTES.some((r) => pathname.startsWith(r))) return 2;
  if (USER_ROUTES.some((r) => pathname.startsWith(r))) return 1;
  return 1;
}

export function middleware(request: NextRequest) {
  if (!AUTH_ENABLED) {
    return NextResponse.next();
  }

  const { pathname } = request.nextUrl;

  if (
    pathname.startsWith('/_next') ||
    pathname.startsWith('/api') ||
    pathname === '/login' ||
    pathname === '/favicon.ico'
  ) {
    return NextResponse.next();
  }

  const session = request.cookies.get(SESSION_COOKIE)?.value;
  if (!session && pathname !== '/login') {
    const loginUrl = new URL('/login', request.url);
    loginUrl.searchParams.set('from', pathname);
    return NextResponse.redirect(loginUrl);
  }

  if (session && pathname === '/login') {
    return NextResponse.redirect(new URL('/dashboard', request.url));
  }

  const role = request.cookies.get(ROLE_COOKIE)?.value || 'worker';
  const required = minRoleForPath(pathname);
  if (roleRank(role) < required) {
    return NextResponse.redirect(new URL('/dashboard', request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/((?!_next/static|_next/image).*)'],
};
