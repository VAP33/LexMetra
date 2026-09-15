import { AlertTriangle, ArrowRight, LoaderCircle, ScanLine } from "lucide-react";
import { useState } from "react";

import { ApiError, login, type AuthedUser } from "@/lib/api-client";
import { Button } from "@/components/ui";

/** Matches dashboard.html's Sign In + Quick Admin / Quick Inspector buttons. */
export function LoginView({ onLoggedIn }: { onLoggedIn: (user: AuthedUser) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | undefined>(undefined);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    await doLogin(username.trim(), password);
  }

  async function doLogin(u: string, p: string) {
    if (!u || !p) return;
    setSubmitting(true);
    setError(undefined);
    try {
      const user = await login(u, p);
      onLoggedIn(user);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in.");
    } finally {
      setSubmitting(false);
    }
  }

  async function quickDemoLogin(demoUser: string) {
    setUsername(demoUser);
    setPassword("password123");
    await doLogin(demoUser, "password123");
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <form onSubmit={handleSubmit} className="w-full max-w-sm rounded-2xl border border-border/70 bg-card p-7 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground"><ScanLine className="h-5 w-5" /></div>
          <div>
            <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">THE INSPECTORS</p>
            <h1 className="text-lg font-semibold tracking-[-.03em]">Sign in</h1>
          </div>
        </div>
        <p className="mt-4 text-sm text-muted-foreground">Every inspection action on this backend requires an authenticated inspector, reviewer, or admin account.</p>
        <div className="mt-6 space-y-4">
          <div>
            <label className="text-xs font-semibold text-muted-foreground">Username</label>
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" className="mt-1.5 h-11 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15" />
          </div>
          <div>
            <label className="text-xs font-semibold text-muted-foreground">Password</label>
            <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" autoComplete="current-password" className="mt-1.5 h-11 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15" />
          </div>
        </div>
        <div className="mt-4 rounded-xl border border-border/60 bg-muted/40 p-3">
          <p className="text-[11px] font-medium text-muted-foreground mb-2">Demo login (requires LMPC_BOOTSTRAP_DEMO_USERS on the backend):</p>
          <div className="flex gap-2">
            <button
              type="button"
              id="fill-admin-btn"
              onClick={() => void quickDemoLogin("admin")}
              className="flex-1 rounded-lg border border-border/80 bg-background py-1.5 text-xs font-medium hover:bg-muted transition-colors"
            >
              Quick Admin
            </button>
            <button
              type="button"
              id="fill-inspector-btn"
              onClick={() => void quickDemoLogin("inspector")}
              className="flex-1 rounded-lg border border-border/80 bg-background py-1.5 text-xs font-medium hover:bg-muted transition-colors"
            >
              Quick Inspector
            </button>
          </div>
        </div>
        {error && <div className="mt-4 flex items-center gap-2 rounded-lg bg-danger-soft px-3 py-2 text-xs text-destructive"><AlertTriangle className="h-4 w-4 shrink-0" />{error}</div>}
        <Button type="submit" className="mt-4 w-full" disabled={submitting || !username || !password}>
          {submitting ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
          {submitting ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </div>
  );
}
