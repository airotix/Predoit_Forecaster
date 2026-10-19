"use client";

import { useCallback, useEffect, useState } from "react";
import AppShell from "@/components/layout/AppShell";
import { useAuth } from "@/components/auth/AuthProvider";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  Mail,
  Shield,
  User as UserIcon,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { roleMeetsRequired, type PreduitRole } from "@/lib/auth/msalConfig";
import { listUsers, updateUserRole, type ManagedUser } from "@/lib/api/auth";

const ROLE_OPTIONS: PreduitRole[] = ["owner", "admin", "manager", "worker"];

const ROLE_STYLES: Record<PreduitRole, string> = {
  owner: "border-purple-500 text-purple-600 dark:text-purple-300",
  admin: "border-blue-500 text-blue-600 dark:text-blue-300",
  manager: "border-emerald-500 text-emerald-600 dark:text-emerald-300",
  worker: "border-slate-400 text-slate-500 dark:text-slate-400",
};

export default function SettingsPage() {
  const { role } = useAuth();
  const canManageUsers = roleMeetsRequired(role, "admin");

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
          <p className="mt-1 text-slate-500 dark:text-slate-400">
            Manage your profile and, if you&apos;re an admin, your team&apos;s access.
          </p>
        </div>

        <Tabs defaultValue="profile" className="space-y-4">
          <TabsList>
            <TabsTrigger value="profile">
              <UserIcon className="mr-2 h-4 w-4" />
              Profile
            </TabsTrigger>
            {canManageUsers && (
              <TabsTrigger value="users">
                <Users className="mr-2 h-4 w-4" />
                User Management
              </TabsTrigger>
            )}
          </TabsList>

          <TabsContent value="profile">
            <ProfileTab />
          </TabsContent>

          {canManageUsers && (
            <TabsContent value="users">
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
    <Card>
      <CardHeader>
        <CardTitle>Profile</CardTitle>
        <CardDescription>Your account details.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="flex items-center gap-4">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-blue-100 text-2xl font-semibold text-blue-700 dark:bg-blue-950 dark:text-blue-300">
            {(name !== "—" ? name : email).charAt(0).toUpperCase()}
          </div>
          <div>
            <div className="text-lg font-semibold text-slate-900 dark:text-white">
              {name}
            </div>
            <div className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400">
              <Mail className="h-3.5 w-3.5" />
              {email}
            </div>
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Role">
            <Badge variant="outline" className={cn("capitalize", ROLE_STYLES[role])}>
              <Shield className="mr-1 h-3 w-3" />
              {role}
            </Badge>
          </Field>
          <Field label="Sign-in method">
            <span className="text-sm text-slate-700 dark:text-slate-300">{methodLabel}</span>
          </Field>
        </div>

        <p className="rounded-lg bg-slate-50 p-3 text-xs text-slate-500 dark:bg-slate-900 dark:text-slate-400">
          Your role determines what you can access. To change it, contact an administrator.
        </p>
      </CardContent>
    </Card>
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
    <Card>
      <CardHeader>
        <CardTitle>User Management</CardTitle>
        <CardDescription>
          Manage roles for email/password accounts. Microsoft SSO users are managed in
          Azure Entra ID.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error && (
          <div className="mb-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-300">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-12 text-slate-400">
            <Loader2 className="h-5 w-5 animate-spin" />
          </div>
        ) : users.length === 0 ? (
          <div className="py-12 text-center text-sm text-slate-500">
            No local accounts yet.
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border border-slate-200 dark:border-slate-800">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-900 dark:text-slate-400">
                <tr>
                  <th className="px-4 py-3 font-medium">User</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Last login</th>
                  <th className="px-4 py-3 font-medium">Role</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {users.map((u) => {
                  const isSelf =
                    currentUser?.email?.toLowerCase() === u.email.toLowerCase();
                  return (
                    <tr key={u.email} className="hover:bg-slate-50 dark:hover:bg-slate-900/50">
                      <td className="px-4 py-3">
                        <div className="font-medium text-slate-900 dark:text-white">
                          {u.name || u.email.split("@")[0]}
                          {isSelf && (
                            <span className="ml-2 text-xs font-normal text-slate-400">
                              (you)
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-slate-500">{u.email}</div>
                      </td>
                      <td className="px-4 py-3">
                        <Badge
                          variant="outline"
                          className={cn(
                            "capitalize",
                            u.status === "active"
                              ? "border-emerald-500 text-emerald-600"
                              : "border-slate-400 text-slate-500"
                          )}
                        >
                          {u.status}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-slate-500">
                        {u.last_login_at
                          ? new Date(u.last_login_at).toLocaleDateString()
                          : "Never"}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <Select
                            value={u.role}
                            onValueChange={(v) => handleRoleChange(u, v as PreduitRole)}
                            disabled={isSelf || savingEmail === u.email}
                          >
                            <SelectTrigger className="w-32 capitalize">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {ROLE_OPTIONS.map((r) => (
                                <SelectItem key={r} value={r} className="capitalize">
                                  {r}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          {savingEmail === u.email && (
                            <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
                          )}
                          {savedEmail === u.email && (
                            <CheckCircle2 className="h-4 w-4 text-emerald-500" />
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

        <p className="mt-4 text-xs text-slate-400">
          You can&apos;t change your own role. Owner and admin have full access; managers
          can override and approve; workers have view-only access.
        </p>
      </CardContent>
    </Card>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-400">
        {label}
      </div>
      <div>{children}</div>
    </div>
  );
}
