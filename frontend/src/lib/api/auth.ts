import { PreduitRole } from '@/lib/auth/msalConfig';
import { apiClient } from './client';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:4000/api';

export interface AuthConfig {
  authEnabled: boolean;
  authActive: boolean;
  ssoEnabled: boolean;
  passwordEnabled: boolean;
  signupAllowed: boolean;
  devMode: boolean;
  devRole: PreduitRole;
  roles: PreduitRole[];
}

export interface AuthUser {
  id: string | number;
  email: string;
  name: string;
  role: PreduitRole;
  status?: string;
}

export interface AuthSession {
  token: string;
  user: AuthUser;
  expiresInHours: number;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const message =
      (data && (data.detail || data.message)) || 'Something went wrong. Please try again.';
    throw new Error(typeof message === 'string' ? message : 'Request failed.');
  }
  return data as T;
}

export async function fetchAuthConfig(): Promise<AuthConfig> {
  const res = await fetch(`${API_BASE}/auth/config`);
  if (!res.ok) throw new Error('Unable to reach the authentication service.');
  return res.json();
}

export function loginWithPassword(email: string, password: string): Promise<AuthSession> {
  return post<AuthSession>('/auth/login', { email, password });
}

export function signupWithPassword(
  email: string,
  password: string,
  name: string
): Promise<AuthSession> {
  return post<AuthSession>('/auth/signup', { email, password, name });
}

// ── User management (admin / owner) ──

export interface ManagedUser {
  id: number;
  email: string;
  name: string;
  role: PreduitRole;
  status: string;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
}

export function listUsers(): Promise<{ users: ManagedUser[] }> {
  return apiClient.get<{ users: ManagedUser[] }>('/auth/users');
}

export function updateUserRole(email: string, role: PreduitRole): Promise<{ user: AuthUser }> {
  return apiClient.put<{ user: AuthUser }>('/auth/users/role', { email, role });
}
