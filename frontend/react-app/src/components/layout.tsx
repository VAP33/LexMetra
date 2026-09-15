import {
  ClipboardCheck,
  History as HistoryIcon,
  LayoutDashboard,
  Menu,
  ScanLine,
  ShieldAlert,
  ShieldCheck,
  UserRound,
  WifiOff,
  type LucideIcon,
} from "lucide-react";

import type { View } from "@/lib/views";

const navItems: Array<{ label: string; view: View; icon: LucideIcon }> = [
  { label: "Home", view: "home", icon: LayoutDashboard },
  { label: "History", view: "history", icon: HistoryIcon },
  { label: "Register", view: "register", icon: ClipboardCheck },
  { label: "Review", view: "reviewQueue", icon: ShieldAlert },
  { label: "Profile", view: "profile", icon: UserRound },
];

export function AppHeader({
  title,
  eyebrow = "The Inspectors",
  onMenu,
  online,
}: {
  title: string;
  eyebrow?: string;
  onMenu?: () => void;
  online?: boolean;
}) {
  return (
    <header className="sticky top-0 z-30 border-b border-border/70 bg-background/95 backdrop-blur md:border-b-0">
      <div className="mx-auto flex h-[72px] max-w-6xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-3">
          <button type="button" aria-label="Open navigation" onClick={onMenu} className="rounded-lg p-2 text-muted-foreground hover:bg-muted md:hidden">
            <Menu className="h-5 w-5" />
          </button>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[.18em] text-muted-foreground">{eyebrow}</p>
            <h1 className="mt-0.5 text-lg font-semibold tracking-[-.03em] text-foreground">{title}</h1>
          </div>
        </div>
        <div className="hidden items-center gap-3 md:flex">
          {online === false ? (
            <span className="inline-flex items-center gap-2 rounded-full bg-danger-soft px-3 py-1.5 text-xs font-semibold text-destructive">
              <WifiOff className="h-3.5 w-3.5" />Offline
            </span>
          ) : (
            <span className="inline-flex items-center gap-2 rounded-full bg-success-soft px-3 py-1.5 text-xs font-semibold text-success">
              <span className="h-1.5 w-1.5 rounded-full bg-success" />Live
            </span>
          )}
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-primary-foreground"><UserRound className="h-4 w-4" /></div>
        </div>
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-primary-foreground md:hidden"><UserRound className="h-4 w-4" /></div>
      </div>
    </header>
  );
}

export function DesktopRail({ view, onNavigate }: { view: View; onNavigate: (view: View) => void }) {
  return (
    <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 flex-col border-r border-border/70 bg-card px-4 py-6 md:flex">
      <div className="mb-10 flex items-center gap-3 px-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary text-primary-foreground"><ScanLine className="h-5 w-5" /></div>
        <div>
          <p className="text-sm font-bold tracking-[-.03em]">THE INSPECTORS</p>
          <p className="text-[10px] font-bold uppercase tracking-[.12em] text-muted-foreground">SIH 2026 · PS 26034</p>
        </div>
      </div>
      <nav className="space-y-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = view === item.view;
          return (
            <button key={item.view} type="button" onClick={() => onNavigate(item.view)} className={`flex w-full items-center gap-3 rounded-xl px-3 py-3 text-sm font-semibold transition-colors ${active ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/70 hover:text-foreground"}`}>
              <Icon className="h-[18px] w-[18px]" />{item.label}
            </button>
          );
        })}
      </nav>
      <div className="mt-auto rounded-2xl bg-muted p-4">
        <div className="flex items-center gap-2 text-xs font-semibold text-foreground"><ShieldCheck className="h-4 w-4 text-brand" />Live compliance engine</div>
        <p className="mt-2 text-xs leading-5 text-muted-foreground">Real OCR extraction and deterministic rule evaluation are active.</p>
      </div>
    </aside>
  );
}

export function BottomNav({ view, onNavigate }: { view: View; onNavigate: (view: View) => void }) {
  return (
    <nav className="safe-bottom fixed inset-x-0 bottom-0 z-40 border-t border-border/70 bg-card/95 px-3 pt-2 backdrop-blur md:hidden">
      <div className="mx-auto grid max-w-lg grid-cols-5 items-end">
        <NavButton label="Home" icon={LayoutDashboard} active={view === "home"} onClick={() => onNavigate("home")} />
        <NavButton label="History" icon={HistoryIcon} active={view === "history"} onClick={() => onNavigate("history")} />
        <div className="relative -top-5 flex justify-center">
          <button type="button" aria-label="Start a scan" onClick={() => onNavigate("scan")} className="flex h-16 w-16 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-xl shadow-primary/20 transition-transform active:scale-95">
            <ScanLine className="h-7 w-7" />
          </button>
        </div>
        <NavButton label="Review" icon={ShieldAlert} active={view === "reviewQueue"} onClick={() => onNavigate("reviewQueue")} />
        <NavButton label="Profile" icon={UserRound} active={view === "profile"} onClick={() => onNavigate("profile")} />
      </div>
    </nav>
  );
}

function NavButton({ label, icon: Icon, active, onClick }: { label: string; icon: LucideIcon; active: boolean; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className={`flex min-h-14 flex-col items-center justify-center gap-1 text-[10px] font-semibold ${active ? "text-brand" : "text-muted-foreground"}`}>
      <Icon className="h-[18px] w-[18px]" /><span>{label}</span>
    </button>
  );
}
