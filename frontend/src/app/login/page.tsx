'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  AlertCircle,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Eye,
  EyeOff,
  Loader2,
  Lock,
  Mail,
  ShieldCheck,
  Sparkles,
  User,
} from 'lucide-react';
import { useAuth } from '@/components/auth/AuthProvider';
import { fetchAuthConfig, type AuthConfig } from '@/lib/api/auth';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

type Mode = 'signin' | 'signup';

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export default function LoginPage() {
  const router = useRouter();
  const { loginWithPassword, signup, login, isAuthenticated, method } = useAuth();

  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [mode, setMode] = useState<Mode>('signin');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAuthConfig()
      .then(setConfig)
      .catch(() => setConfig(null));
  }, []);

  // Redirect once a real session exists (not the dev synthetic user).
  useEffect(() => {
    if (isAuthenticated && method !== 'dev') {
      const from = new URLSearchParams(window.location.search).get('from');
      router.replace(from && from.startsWith('/') ? from : '/dashboard');
    }
  }, [isAuthenticated, method, router]);

  const switchMode = useCallback((next: Mode) => {
    setMode(next);
    setError(null);
    setPassword('');
    setConfirm('');
  }, []);

  const validate = (): string | null => {
    if (!EMAIL_RE.test(email.trim())) return 'Please enter a valid email address.';
    if (password.length < 8) return 'Password must be at least 8 characters.';
    if (mode === 'signup' && password !== confirm) return 'Passwords do not match.';
    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      if (mode === 'signin') {
        await loginWithPassword(email.trim(), password);
      } else {
        await signup(email.trim(), password, name.trim());
      }
      // Redirect handled by the effect once the session is set.
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to continue. Please try again.');
      setSubmitting(false);
    }
  };

  const devMode = config?.devMode ?? false;
  const ssoEnabled = config?.ssoEnabled ?? false;
  const signupAllowed = config?.signupAllowed ?? true;

  return (
    <div className="min-h-screen w-full lg:grid lg:grid-cols-[1.1fr_1fr] bg-slate-50 dark:bg-slate-950">
      {/* ── Brand / hero panel ── */}
      <div className="relative hidden overflow-hidden bg-gradient-to-br from-blue-700 via-indigo-700 to-slate-900 lg:flex lg:flex-col lg:justify-between p-12 text-white">
        <div
          className="pointer-events-none absolute inset-0 opacity-20"
          style={{
            backgroundImage:
              'radial-gradient(circle at 20% 20%, white 1px, transparent 1px), radial-gradient(circle at 80% 60%, white 1px, transparent 1px)',
            backgroundSize: '48px 48px, 64px 64px',
          }}
        />
        <div className="relative flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-white/15 backdrop-blur">
            <BarChart3 className="h-6 w-6" />
          </div>
          <span className="text-2xl font-semibold tracking-tight">Preduit</span>
        </div>

        <div className="relative space-y-6">
          <h1 className="text-4xl font-bold leading-tight tracking-tight">
            Forecast demand.
            <br />
            Order with confidence.
          </h1>
          <p className="max-w-md text-blue-100/90">
            AI-driven demand forecasting and net-to-order planning for wholesale — from
            ten years of history to next season&apos;s buy.
          </p>
          <ul className="space-y-3 pt-2 text-sm text-blue-50">
            {[
              'SARIMA + CatBoost forecasts across three scenarios',
              'Size-level recommendations with net-to-order logic',
              'Review, override, and lock every buy',
            ].map((feature) => (
              <li key={feature} className="flex items-center gap-3">
                <CheckCircle2 className="h-5 w-5 shrink-0 text-blue-200" />
                <span>{feature}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="relative text-xs text-blue-200/70">
          © {new Date().getFullYear()} Preduit · Secure access
        </div>
      </div>

      {/* ── Form panel ── */}
      <div className="flex min-h-screen items-center justify-center p-6 lg:min-h-0">
        <div className="w-full max-w-md">
          {/* Mobile brand */}
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600 text-white">
              <BarChart3 className="h-5 w-5" />
            </div>
            <span className="text-xl font-semibold tracking-tight text-slate-900 dark:text-white">
              Preduit
            </span>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <div className="mb-6">
              <h2 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">
                {mode === 'signin' ? 'Welcome back' : 'Create your account'}
              </h2>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                {mode === 'signin'
                  ? 'Sign in to access your forecasting workspace.'
                  : 'Set up an account to get started with Preduit.'}
              </p>
            </div>

            {/* Tab switcher */}
            {signupAllowed && (
              <div className="mb-6 grid grid-cols-2 gap-1 rounded-lg bg-slate-100 p-1 dark:bg-slate-800">
                {(['signin', 'signup'] as Mode[]).map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => switchMode(m)}
                    className={cn(
                      'rounded-md py-2 text-sm font-medium transition-all',
                      mode === m
                        ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-950 dark:text-white'
                        : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
                    )}
                  >
                    {m === 'signin' ? 'Sign in' : 'Create account'}
                  </button>
                ))}
              </div>
            )}

            {/* Dev-mode banner */}
            {devMode && (
              <div className="mb-6 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-800/60 dark:bg-amber-950/40">
                <div className="flex items-center gap-2 font-medium text-amber-800 dark:text-amber-300">
                  <ShieldCheck className="h-4 w-4" />
                  Developer mode
                </div>
                <p className="mt-1 text-amber-700/90 dark:text-amber-200/80">
                  Authentication is disabled — you can enter as{' '}
                  <span className="font-semibold">{config?.devRole}</span> without signing in.
                </p>
                <Button
                  type="button"
                  variant="outline"
                  className="mt-3 w-full border-amber-300 bg-white/60 text-amber-900 hover:bg-white dark:border-amber-700 dark:bg-transparent dark:text-amber-200"
                  onClick={() => router.replace('/dashboard')}
                >
                  Continue to dashboard
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </div>
            )}

            {/* Error alert */}
            {error && (
              <div className="mb-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-300">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-4">
              {mode === 'signup' && (
                <Field label="Full name" htmlFor="name" icon={<User className="h-4 w-4" />}>
                  <Input
                    id="name"
                    type="text"
                    autoComplete="name"
                    placeholder="Jane Doe"
                    className="pl-9"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                </Field>
              )}

              <Field label="Email" htmlFor="email" icon={<Mail className="h-4 w-4" />}>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  placeholder="you@company.com"
                  className="pl-9"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </Field>

              <Field label="Password" htmlFor="password" icon={<Lock className="h-4 w-4" />}>
                <Input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                  placeholder={mode === 'signup' ? 'At least 8 characters' : '••••••••'}
                  className="pl-9 pr-10"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((s) => !s)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 transition-colors hover:text-slate-600 dark:hover:text-slate-200"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </Field>

              {mode === 'signup' && (
                <Field
                  label="Confirm password"
                  htmlFor="confirm"
                  icon={<Lock className="h-4 w-4" />}
                >
                  <Input
                    id="confirm"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="new-password"
                    placeholder="Re-enter your password"
                    className="pl-9"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    required
                  />
                </Field>
              )}

              <Button type="submit" className="w-full" disabled={submitting}>
                {submitting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {mode === 'signin' ? 'Signing in…' : 'Creating account…'}
                  </>
                ) : (
                  <>
                    {mode === 'signin' ? 'Sign in' : 'Create account'}
                    <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </Button>
            </form>

            {/* SSO */}
            {ssoEnabled && (
              <>
                <div className="my-6 flex items-center gap-3">
                  <div className="h-px flex-1 bg-slate-200 dark:bg-slate-800" />
                  <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
                    or
                  </span>
                  <div className="h-px flex-1 bg-slate-200 dark:bg-slate-800" />
                </div>
                <Button
                  type="button"
                  variant="outline"
                  className="w-full"
                  onClick={() => login()}
                  disabled={submitting}
                >
                  <MicrosoftLogo />
                  Sign in with Microsoft
                </Button>
              </>
            )}

            {mode === 'signup' && (
              <p className="mt-6 flex items-center justify-center gap-1.5 text-center text-xs text-slate-400">
                <Sparkles className="h-3.5 w-3.5" />
                New accounts start with view-only access. An admin can upgrade your role.
              </p>
            )}
          </div>

          <p className="mt-6 text-center text-sm text-slate-500 dark:text-slate-400">
            {mode === 'signin' ? (
              signupAllowed ? (
                <>
                  Don&apos;t have an account?{' '}
                  <button
                    onClick={() => switchMode('signup')}
                    className="font-medium text-blue-600 hover:underline dark:text-blue-400"
                  >
                    Create one
                  </button>
                </>
              ) : (
                'Contact your administrator for access.'
              )
            ) : (
              <>
                Already have an account?{' '}
                <button
                  onClick={() => switchMode('signin')}
                  className="font-medium text-blue-600 hover:underline dark:text-blue-400"
                >
                  Sign in
                </button>
              </>
            )}
          </p>
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  htmlFor,
  icon,
  children,
}: {
  label: string;
  htmlFor: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label
        htmlFor={htmlFor}
        className="text-sm font-medium text-slate-700 dark:text-slate-300"
      >
        {label}
      </label>
      <div className="relative">
        <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">
          {icon}
        </span>
        {children}
      </div>
    </div>
  );
}

function MicrosoftLogo() {
  return (
    <svg viewBox="0 0 21 21" className="h-4 w-4" aria-hidden="true">
      <rect x="1" y="1" width="9" height="9" fill="#f25022" />
      <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
      <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
      <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
    </svg>
  );
}
