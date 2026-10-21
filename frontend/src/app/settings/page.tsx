"use client";

import { useCallback, useEffect, useState } from "react";
import {
  CheckCircleIcon,
  CircleNotchIcon,
  EnvelopeSimpleIcon,
  IdentificationCardIcon,
  InfoIcon,
  KeyIcon,
  ShieldCheckIcon,
  UserIcon,
  UsersThreeIcon,
} from "@phosphor-icons/react";
import AppShell from "@/components/layout/AppShell";
import { useAuth } from "@/components/auth/AuthProvider";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Notice, PageHeader, Pill, SelectField } from "@/components/ui/brand";
import { cn } from "@/lib/utils";
import { roleMeetsRequired, type PreduitRole } from "@/lib/auth/msalConfig";
import { listUsers, updateUserRole, type ManagedUser } from "@/lib/api/auth";

const ROLE_OPTIONS: PreduitRole[] = ["owner", "admin", "manager", "worker"];

const ROLE_TONES: Record<PreduitRole, "plum" | "brand" | "success" | "neutral"> = {
  owner: "plum",
  admin: "brand",
  manager: "success",
  worker: "neutral",
};

const TAB_TRIGGER =
  "h-10 gap-2 rounded-full px-[18px] text-sm font-semibold text-fg-2 shadow-none hover:text-fg-1 focus-visible:ring-0 focus-visible:shadow-[0_0_0_3px_rgba(245,130,32,0.35)] data-[state=active]:bg-card data-[state=active]:font-bold data-[state=active]:text-fg-1 data-[state=active]:shadow-card [&_svg]:h-[17px] [&_svg]:w-[17px]";

export default function SettingsPage() {
  const { role } = useAuth();
  const canManageUsers = roleMeetsRequired(role, "admin");

  return (
    <AppShell>
      <div className="mx-auto flex w-full max-w-[1040px] flex-col gap-6">
        <PageHeader
          eyebrow="Account & access"
          title="Settings"
          description={<>Manage your profile and, if you&apos;re an admin, your team&apos;s access.</>}
        />

        <Tabs defaultValue="profile" className="flex flex-col gap-5">
          <TabsList className="h-auto self-start rounded-full bg-soft p-1">
            <TabsTrigger value="profile" className={TAB_TRIGGER}>
              <UserIcon weight="bold" />
              Profile
            </TabsTrigger>
            {canManageUsers && (
              <TabsTrigger value="users" className={TAB_TRIGGER}>
                <UsersThreeIcon weight="bold" />
                User Management
              </TabsTrigger>
            )}
          </TabsList>

          <TabsContent value="profile" className="mt-0 focus-visible:ring-0">
            <ProfileTab />
          </TabsContent>

          {canManageUsers && (
            <TabsContent value="users" className="mt-0 focus-visible:ring-0">
              <UserManagementTab />
            </TabsContent>
          )}
        </Tabs>
      </div>
    </AppShell>
  );
}

function ProfileTab() {
  const { user, role, method } = useAuth();
  const name = user?.name || "—";
  const email = user?.email || "—";

  const methodLabel =
    method === "password"
      ? "Email & password"
      : method === "sso"
      ? "Microsoft SSO"
      : method === "dev"
      ? "Developer mode"
      : "—";

  return (
    <section className="flex flex-col gap-6 rounded-[32px] border border-line bg-card p-6 shadow-card sm:p-8">
      <div className="flex flex-col gap-1.5">
        <h2 className="flex items-center gap-2.5 text-[22px] font-extrabold tracking-[-0.02em]">
          <IdentificationCardIcon className="h-[22px] w-[22px] text-brand" />
          Profile
        </h2>
        <p className="text-sm leading-relaxed text-fg-2">Your account details.</p>
      </div>

      <div className="flex items-center gap-4 rounded-3xl bg-champagne p-5">
        <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-plum-50 font-display text-2xl font-bold text-plum-600">
          {(name !== "—" ? name : email).charAt(0).toUpperCase()}
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <div className="truncate font-display text-xl font-bold tracking-[-0.01em] text-fg-1">
            {name}
          </div>
          <div className="flex min-w-0 items-center gap-1.5 text-sm text-fg-2">
            <EnvelopeSimpleIcon className="h-4 w-4 shrink-0 text-fg-3" />
            <span className="truncate">{email}</span>
          </div>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Role" icon={<ShieldCheckIcon className="h-[18px] w-[18px]" />}>
          <Pill tone={ROLE_TONES[role]} className="capitalize">
            {role}
          </Pill>
        </Field>
        <Field label="Sign-in method" icon={<KeyIcon className="h-[18px] w-[18px]" />}>
          <span className="text-[15px] font-semibold text-fg-1">{methodLabel}</span>
        </Field>
      </div>

      <Notice tone="info">
        Your role determines what you can access. To change it, contact an administrator.
      </Notice>
    </section>
  );
}

function UserManagementTab() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingEmail, setSavingEmail] = useState<string | null>(null);
  const [savedEmail, setSavedEmail] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    listUsers()
      .then((res) => setUsers(res.users))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load users."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleRoleChange = async (target: ManagedUser, nextRole: PreduitRole) => {
    if (nextRole === target.role) return;
    setSavingEmail(target.email);
    setSavedEmail(null);
    setError(null);
    const previous = users;
    setUsers((prev) =>
      prev.map((u) => (u.email === target.email ? { ...u, role: nextRole } : u))
    );
    try {
      await updateUserRole(target.email, nextRole);
      setSavedEmail(target.email);
      setTimeout(() => setSavedEmail(null), 2000);
    } catch (e) {
      setUsers(previous); // rollback
      setError(e instanceof Error ? e.message : "Failed to update role.");
    } finally {
      setSavingEmail(null);
    }
  };

  return (
    <section className="overflow-hidden rounded-[32px] border border-line bg-card shadow-card">
      <div className="flex flex-col gap-1.5 border-b border-line px-6 py-6 sm:px-8">
        <h2 className="flex items-center gap-2.5 text-[22px] font-extrabold tracking-[-0.02em]">
          <UsersThreeIcon className="h-[22px] w-[22px] text-brand" />
          User Management
        </h2>
        <p className="max-w-[760px] text-pretty text-sm leading-relaxed text-fg-2">
          Manage roles for email/password accounts. Microsoft SSO users are managed in
          Azure Entra ID.
        </p>
      </div>

      {error && (
        <div className="px-6 pt-5 sm:px-8">
          <Notice tone="danger">{error}</Notice>
        </div>
      )}

      {loading ? (
        <div role="status" aria-label="Loading users" className="flex items-center justify-center py-14 text-fg-3">
          <CircleNotchIcon className="h-6 w-6 animate-spin" />
        </div>
      ) : users.length === 0 ? (
        <div className="py-14 text-center text-sm text-fg-3">No local accounts yet.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="border-b border-line bg-page text-left text-[11px] font-bold uppercase tracking-[0.1em] text-fg-3">
              <tr>
                <th className="px-6 py-3 sm:px-8">User</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Last login</th>
                <th className="px-6 py-3 sm:px-8">Role</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {users.map((u) => {
                const isSelf =
                  currentUser?.email?.toLowerCase() === u.email.toLowerCase();
                const display = u.name || u.email.split("@")[0];
                return (
                  <tr key={u.email} className="transition-colors hover:bg-page">
                    <td className="px-6 py-3.5 sm:px-8">
                      <div className="flex min-w-0 items-center gap-3">
                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-plum-50 text-[13px] font-bold text-plum-600">
                          {display.charAt(0).toUpperCase()}
                        </span>
                        <span className="flex min-w-0 flex-col">
                          <span className="font-semibold text-fg-1">
                            {display}
                            {isSelf && (
                              <span className="ml-2 text-xs font-normal text-fg-3">(you)</span>
                            )}
                          </span>
                          <span className="truncate text-xs text-fg-3">{u.email}</span>
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3.5">
                      <Pill tone={u.status === "active" ? "success" : "neutral"} className="capitalize">
                        {u.status}
                      </Pill>
                    </td>
                    <td className="px-4 py-3.5 font-mono text-[13px] text-fg-2">
                      {u.last_login_at
                        ? new Date(u.last_login_at).toLocaleDateString()
                        : "Never"}
                    </td>
                    <td className="px-6 py-3.5 sm:px-8">
                      <div className="flex items-center gap-2">
                        <SelectField
                          aria-label={`Role for ${u.email}`}
                          wrapperClassName="w-36"
                          className="h-10 capitalize"
                          value={u.role}
                          onChange={(e) => void handleRoleChange(u, e.target.value as PreduitRole)}
                          disabled={isSelf || savingEmail === u.email}
                        >
                          {ROLE_OPTIONS.map((r) => (
                            <option key={r} value={r} className="capitalize">
                              {r}
                            </option>
                          ))}
                        </SelectField>
                        {savingEmail === u.email && (
                          <CircleNotchIcon aria-label="Saving" className="h-[18px] w-[18px] animate-spin text-fg-3" />
                        )}
                        {savedEmail === u.email && (
                          <CheckCircleIcon weight="fill" aria-label="Saved" className="h-[18px] w-[18px] text-success-600" />
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex items-start gap-3 border-t border-line bg-page px-6 py-5 sm:px-8">
        <InfoIcon className="mt-0.5 h-[18px] w-[18px] shrink-0 text-plum-600" />
        <p className="text-pretty text-[13px] leading-relaxed text-fg-2">
          You can&apos;t change your own role. Owner and admin have full access; managers
          can override and approve; workers have view-only access.
        </p>
      </div>
    </section>
  );
}

function Field({
  label,
  icon,
  children,
}: {
  label: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("flex items-center gap-3.5 rounded-[20px] border border-line bg-card p-4")}>
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[14px] bg-brand-50 text-brand-700">
        {icon}
      </span>
      <div className="flex min-w-0 flex-col gap-1.5">
        <div className="text-[11px] font-bold uppercase tracking-[0.1em] text-fg-3">{label}</div>
        <div>{children}</div>
      </div>
    </div>
  );
}
