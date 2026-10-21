'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ArrowRightIcon,
  CheckCircleIcon,
  CircleNotchIcon,
  EnvelopeSimpleIcon,
  EyeIcon,
  EyeSlashIcon,
  LockSimpleIcon,
  ShieldCheckIcon,
  SparkleIcon,
  UserIcon,
} from '@phosphor-icons/react';
import { useAuth } from '@/components/auth/AuthProvider';
import { fetchAuthConfig, type AuthConfig } from '@/lib/api/auth';
import { BrandMark } from '@/components/layout/Sidebar';
import { ModeToggle } from '@/components/mode-toggle';
import { BrandButton } from '@/components/ui/brand-button';
import { Notice, TextField } from '@/components/ui/brand';
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
    <div className="min-h-screen w-full bg-page text-fg-1 lg:grid lg:grid-cols-[1.05fr_1fr] lg:gap-4 lg:p-4">
      {/* ── Brand / hero panel ── */}
      <div className="relative hidden overflow-hidden rounded-[32px] bg-champagne p-12 lg:flex lg:flex-col lg:justify-between">
        <div
          aria-hidden
          className="pointer-events-none absolute -right-32 -top-32 h-[520px] w-[520px] rounded-full bg-[radial-gradient(circle,var(--glow),rgba(245,130,32,0)_70%)]"
        />
        <div className="relative flex items-center gap-3">
          <BrandMark />
          <span className="flex flex-col gap-px">
            <span className="font-display text-xl font-bold tracking-[-0.02em]">Preduit</span>
            <span className="text-xs text-fg-3">Demand planning</span>
          </span>
        </div>

        <div className="relative flex max-w-[520px] flex-col gap-6">
          <h1 className="font-display text-[44px] font-extrabold leading-[1.06] tracking-[-0.02em]">
            Forecast demand.
            <br />
            Order with confidence.
          </h1>
          <p className="max-w-md text-pretty text-base leading-relaxed text-fg-2">
            AI-driven demand forecasting and net-to-order planning for wholesale — from
            ten years of history to next season&apos;s buy.
          </p>
          <ul className="flex flex-col gap-2.5 pt-2">
            {[
              'SARIMA + CatBoost forecasts across three scenarios',
              'Size-level recommendations with net-to-order logic',
              'Review, override, and lock every buy',
            ].map((feature) => (
              <li
                key={feature}
                className="flex items-center gap-3 text-[15px] font-semibold text-fg-1"
              >
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-card text-success-600 shadow-card">
                  <CheckCircleIcon weight="fill" className="h-[18px] w-[18px]" />
                </span>
                <span>{feature}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="relative text-xs text-fg-3">
          © {new Date().getFullYear()} Preduit · Secure access
        </div>
      </div>

      {/* ── Form panel ── */}
      <div className="relative flex min-h-screen flex-col px-4 py-6 sm:px-6 lg:min-h-0 lg:py-4">
        <div className="flex items-center justify-between gap-3">
          {/* Mobile brand */}
          <div className="flex items-center gap-3 lg:invisible">
            <BrandMark />
            <span className="flex flex-col gap-px">
              <span className="font-display text-xl font-bold tracking-[-0.02em]">Preduit</span>
              <span className="text-xs text-fg-3">Demand planning</span>
            </span>
          </div>
          <ModeToggle />
        </div>

        <div className="flex flex-1 items-center justify-center py-8">
          <div className="w-full max-w-[440px]">
            <div className="rounded-[32px] border border-line bg-card p-6 shadow-card sm:p-8">
              <div className="mb-6 flex flex-col gap-1.5">
                <span className="text-xs font-bold uppercase tracking-[0.12em] text-brand">
                  Preduit
                </span>
                <h2 className="font-display text-[28px] font-extrabold leading-[1.1] tracking-[-0.02em] sm:text-[32px]">
                  {mode === 'signin' ? 'Welcome back' : 'Create your account'}
                </h2>
                <p className="text-sm leading-relaxed text-fg-2">
                  {mode === 'signin'
                    ? 'Sign in to access your forecasting workspace.'
                    : 'Set up an account to get started with Preduit.'}
                </p>
              </div>

              {/* Tab switcher */}
              {signupAllowed && (
                <div className="mb-6 grid grid-cols-2 gap-1 rounded-full bg-soft p-1">
                  {(['signin', 'signup'] as Mode[]).map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => switchMode(m)}
                      aria-pressed={mode === m}
                      className={cn(
                        'h-10 rounded-full text-sm transition-all focus-visible:outline-none focus-visible:shadow-[0_0_0_3px_rgba(245,130,32,0.35)]',
                        mode === m
                          ? 'bg-card font-bold text-fg-1 shadow-card'
                          : 'font-semibold text-fg-2 hover:text-fg-1'
                      )}
                    >
                      {m === 'signin' ? 'Sign in' : 'Create account'}
                    </button>
                  ))}
                </div>
              )}

              {/* Dev-mode banner */}
              {devMode && (
                <div className="mb-6 flex flex-col gap-3 rounded-[20px] border border-brand-200 bg-brand-50 p-[18px] text-sm">
                  <div className="flex items-center gap-2 font-bold text-brand-800">
                    <ShieldCheckIcon weight="fill" className="h-[18px] w-[18px]" />
                    Developer mode
                  </div>
                  <p className="leading-relaxed text-fg-2">
                    Authentication is disabled — you can enter as{' '}
                    <span className="font-semibold text-fg-1">{config?.devRole}</span> without signing in.
                  </p>
                  <BrandButton
                    variant="outline"
                    className="w-full bg-card"
                    onClick={() => router.replace('/dashboard')}
                  >
                    Continue to dashboard
                    <ArrowRightIcon />
                  </BrandButton>
                </div>
              )}

              {/* Error alert */}
              {error && (
                <Notice tone="danger" className="mb-4">
                  {error}
                </Notice>
              )}

              {/* Form */}
              <form onSubmit={handleSubmit} className="flex flex-col gap-4">
                {mode === 'signup' && (
                  <Field label="Full name" htmlFor="name" icon={<UserIcon className="h-[18px] w-[18px]" />}>
                    <TextField
                      id="name"
                      type="text"
                      autoComplete="name"
                      placeholder="Jane Doe"
                      className="h-[52px] w-full rounded-[14px] pl-11 text-[15px]"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                    />
                  </Field>
                )}

                <Field label="Email" htmlFor="email" icon={<EnvelopeSimpleIcon className="h-[18px] w-[18px]" />}>
                  <TextField
                    id="email"
                    type="email"
                    autoComplete="email"
                    placeholder="you@company.com"
                    className="h-[52px] w-full rounded-[14px] pl-11 text-[15px]"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                  />
                </Field>

                <Field label="Password" htmlFor="password" icon={<LockSimpleIcon className="h-[18px] w-[18px]" />}>
                  <TextField
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                    placeholder={mode === 'signup' ? 'At least 8 characters' : '••••••••'}
                    className="h-[52px] w-full rounded-[14px] pl-11 pr-12 text-[15px]"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((s) => !s)}
                    className="absolute right-2 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-[10px] text-fg-3 transition-colors hover:bg-soft hover:text-fg-1"
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                    tabIndex={-1}
                  >
                    {showPassword ? (
                      <EyeSlashIcon className="h-[18px] w-[18px]" />
                    ) : (
                      <EyeIcon className="h-[18px] w-[18px]" />
                    )}
                  </button>
                </Field>

                {mode === 'signup' && (
                  <Field
                    label="Confirm password"
                    htmlFor="confirm"
                    icon={<LockSimpleIcon className="h-[18px] w-[18px]" />}
                  >
                    <TextField
                      id="confirm"
                      type={showPassword ? 'text' : 'password'}
                      autoComplete="new-password"
                      placeholder="Re-enter your password"
                      className="h-[52px] w-full rounded-[14px] pl-11 text-[15px]"
                      value={confirm}
                      onChange={(e) => setConfirm(e.target.value)}
                      required
                    />
                  </Field>
                )}

                <BrandButton type="submit" size="lg" className="mt-1 w-full" disabled={submitting}>
                  {submitting ? (
                    <>
                      <CircleNotchIcon className="animate-spin" />
                      {mode === 'signin' ? 'Signing in…' : 'Creating account…'}
                    </>
                  ) : (
                    <>
                      {mode === 'signin' ? 'Sign in' : 'Create account'}
                      <ArrowRightIcon />
                    </>
                  )}
                </BrandButton>
              </form>

              {/* SSO */}
              {ssoEnabled && (
                <>
                  <div className="my-6 flex items-center gap-3">
                    <div className="h-px flex-1 bg-line" />
                    <span className="text-[11px] font-bold uppercase tracking-[0.12em] text-fg-3">
                      or
                    </span>
                    <div className="h-px flex-1 bg-line" />
                  </div>
                  <BrandButton
                    variant="outline"
                    size="lg"
                    className="w-full"
                    onClick={() => login()}
                    disabled={submitting}
                  >
                    <MicrosoftLogo />
                    Sign in with Microsoft
                  </BrandButton>
                </>
              )}

              {mode === 'signup' && (
                <p className="mt-6 flex items-center justify-center gap-1.5 text-center text-xs leading-relaxed text-fg-3">
                  <SparkleIcon weight="fill" className="h-3.5 w-3.5 shrink-0 text-brand" />
                  New accounts start with view-only access. An admin can upgrade your role.
                </p>
              )}
            </div>

            <p className="mt-6 text-center text-sm text-fg-2">
              {mode === 'signin' ? (
                signupAllowed ? (
                  <>
                    Don&apos;t have an account?{' '}
                    <button
                      onClick={() => switchMode('signup')}
                      className="font-bold text-brand-700 hover:text-brand-800 hover:underline"
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
                    className="font-bold text-brand-700 hover:text-brand-800 hover:underline"
                  >
                    Sign in
                  </button>
                </>
              )}
            </p>

            <p className="mt-3 text-center text-xs text-fg-3 lg:hidden">
              © {new Date().getFullYear()} Preduit · Secure access
            </p>
          </div>
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
    <div className="flex flex-col gap-2">
      <label htmlFor={htmlFor} className="text-sm font-bold text-fg-1">
        {label}
      </label>
      <div className="relative">
        <span className="pointer-events-none absolute left-4 top-1/2 z-[1] -translate-y-1/2 text-fg-3">
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
