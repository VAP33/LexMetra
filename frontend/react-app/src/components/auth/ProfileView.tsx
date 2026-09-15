import { BadgeCheck, Bell, ChevronRight, CircleHelp, LogOut, ScanLine, Settings2, ShieldCheck, Sparkles, UserRound, type LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";

import { checkHealth, type AuthedUser } from "@/lib/api-client";
import { AppHeader } from "@/components/layout";
import { Button } from "@/components/ui";

export function ProfileView({ user, onLogout }: { user: AuthedUser | null; onLogout: () => void }) {
  const [health, setHealth] = useState<"checking" | "ok" | "down">("checking");
  useEffect(() => {
    let cancelled = false;
    checkHealth().then((result) => { if (!cancelled) setHealth(result ? "ok" : "down"); });
    return () => { cancelled = true; };
  }, []);

  const systemRows: Array<[LucideIcon, string, string, "ok" | "checking" | "down"]> = [
    [ScanLine, "Inspection engine", health === "ok" ? "Connected · live" : health === "checking" ? "Checking…" : "Unreachable", health],
    [Sparkles, "OCR extraction", "Tesseract + rule-based classification", "ok"],
    [ShieldCheck, "Evidence storage", "Original images retained server-side per inspection", "ok"],
  ];

  return (
    <>
      <AppHeader title="Inspector profile" />
      <main className="mx-auto max-w-3xl space-y-5 px-4 pb-28 pt-6 sm:px-6 md:pb-10 lg:px-8 lg:pt-10">
        <section className="flex items-center gap-4 rounded-2xl border border-border/70 bg-card p-5 sm:p-7">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary text-primary-foreground"><UserRound className="h-7 w-7" /></div>
          <div>
            <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">{user?.role || "Inspector"}</p>
            <h2 className="mt-1 text-xl font-semibold">{user?.username || "Signed out"}</h2>
            <p className="mt-1 text-sm text-muted-foreground">Legal Metrology unit</p>
          </div>
          <BadgeCheck className="ml-auto h-5 w-5 text-success" />
        </section>
        <section className="rounded-2xl border border-border/70 bg-card">
          <div className="border-b border-border p-5">
            <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">Workspace</p>
            <h3 className="mt-2 text-xl font-semibold">System status</h3>
          </div>
          <div className="divide-y divide-border">
            {systemRows.map(([Icon, label, value, state]) => (
              <div key={label} className="flex items-center gap-3 p-5">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-muted text-brand"><Icon className="h-4 w-4" /></div>
                <div className="flex-1"><p className="text-sm font-semibold">{label}</p><p className="mt-1 text-xs text-muted-foreground">{value}</p></div>
                <span className={`h-2 w-2 rounded-full ${state === "ok" ? "bg-success" : state === "checking" ? "bg-warning" : "bg-destructive"}`} />
              </div>
            ))}
          </div>
        </section>
        <section className="rounded-2xl border border-border/70 bg-card">
          <div className="border-b border-border p-5">
            <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">Preferences</p>
            <h3 className="mt-2 text-xl font-semibold">Settings</h3>
          </div>
          {([[Bell, "Notifications", "Inspection reminders"], [Settings2, "Language", "English (India)"], [CircleHelp, "Help & feedback", "Product guidance"]] as Array<[LucideIcon, string, string]>).map(([Icon, label, value]) => (
            <button type="button" key={label} className="flex w-full items-center gap-3 border-b border-border p-5 text-left last:border-0 hover:bg-muted/50">
              <Icon className="h-5 w-5 text-muted-foreground" />
              <div className="flex-1"><p className="text-sm font-semibold">{label}</p><p className="mt-1 text-xs text-muted-foreground">{value}</p></div>
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
            </button>
          ))}
        </section>
        <Button variant="secondary" className="w-full" onClick={onLogout}><LogOut className="h-4 w-4" />Sign out</Button>
      </main>
    </>
  );
}
