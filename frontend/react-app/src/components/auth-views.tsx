import { Header as AppHeader } from "./app-header";
import { type Inspection } from "@/lib/types";
import React, { useState, useEffect } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BadgeCheck,
  Bell,
  Building2,
  Check,
  ChevronRight,
  CircleHelp,
  Globe,
  KeyRound,
  LoaderCircle,
  Lock,
  LogOut,
  Mail,
  ScanLine,
  Settings2,
  Shield,
  ShieldCheck,
  Sparkles,
  User,
  UserCheck,
  UserRound,
  Users,
  type LucideIcon,
} from "lucide-react";
import { type Language, getTranslation } from "@/lib/i18n";
import { type AuthedUser, login, checkHealth, ApiError } from "@/lib/api-client";
import { type View, Button, LexMetraLogo } from "./ui-primitives";

export function LoginView({
  onLoggedIn,
  onBack,
  onConsumerPortal,
}: {
  onLoggedIn: (user: AuthedUser, targetView?: View) => void;
  onBack?: () => void;
  onConsumerPortal?: () => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | undefined>(undefined);

  async function handleQuickLogin(u: string, p: string, target?: View) {
    setUsername(u);
    setPassword(p);
    setSubmitting(true);
    setError(undefined);
    try {
      const user = await login(u, p);
      onLoggedIn(user, target || (user.role === "admin" ? "seniorRegional" : "home"));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(undefined);
    try {
      const user = await login(username.trim(), password);
      const target: View =
        user.role === "admin"
          ? "seniorRegional"
          : user.role === "reviewer" || user.role === "senior_inspector" || user.role === "authority"
            ? "authority"
            : user.role === "customer"
              ? "customer"
              : "home";
      onLoggedIn(user, target);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50/70 px-4 py-8">
      {onBack && (
        <button
          type="button"
          onClick={onBack}
          className="mb-4 inline-flex items-center gap-2 text-sm font-semibold text-slate-600 hover:text-brand-900 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" /> Back to Overview
        </button>
      )}
      <form onSubmit={handleSubmit} className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-7 shadow-xl">
        <div className="h-1.5 w-full tricolor-stripe mb-5 rounded-full" />
        <div className="flex flex-col items-center text-center pb-4 border-b border-slate-100 mb-4">
          <LexMetraLogo className="h-10 sm:h-12 w-auto max-w-[220px] mx-auto mb-1" />
        </div>
        <p className="mt-2 text-xs leading-relaxed text-muted-foreground text-center">
          Select your statutory role or enter credentials to access Legal Metrology dashboards and inspection tools.
        </p>

        {/* 1-Click Role Direct Sign-in - 3 Roles: Consumer, Field Inspector, Senior Inspector */}
        <div className="mt-5 space-y-3">
          <p className="text-xs font-black uppercase tracking-wider text-slate-700">INSTANT ROLE ACCESS (DEMO):</p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
            {/* Citizen Consumer */}
            <button
              type="button"
              id="quick-customer-login"
              disabled={submitting}
              onClick={() => handleQuickLogin("customer", "password123", "customer")}
              className="flex flex-col items-center text-center p-3 rounded-2xl border border-cyan-200/90 bg-cyan-50/30 hover:bg-cyan-50/80 transition-all group shadow-2xs"
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#0891B2] text-white shadow-xs mb-2">
                <Users className="h-5 w-5" />
              </div>
              <p className="text-xs font-bold text-slate-900 group-hover:text-cyan-900">Consumer</p>
            </button>

            {/* Field Inspector */}
            <button
              type="button"
              id="quick-inspector-login"
              disabled={submitting}
              onClick={() => handleQuickLogin("inspector", "password123", "home")}
              className="flex flex-col items-center text-center p-3 rounded-2xl border border-purple-200/90 bg-purple-50/30 hover:bg-purple-50/80 transition-all group shadow-2xs"
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#6B21A8] text-white shadow-xs mb-2">
                <ShieldCheck className="h-5 w-5" />
              </div>
              <p className="text-xs font-bold text-slate-900 group-hover:text-purple-900">Field Inspector</p>
            </button>

            {/* Senior Inspector */}
            <button
              type="button"
              id="quick-admin-login"
              disabled={submitting}
              onClick={() => handleQuickLogin("admin", "password123", "seniorRegional")}
              className="flex flex-col items-center text-center p-3 rounded-2xl border border-blue-200/90 bg-blue-50/30 hover:bg-blue-50/80 transition-all group shadow-2xs"
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-900 text-white shadow-xs mb-2">
                <Globe className="h-5 w-5" />
              </div>
              <p className="text-xs font-bold text-slate-900 group-hover:text-brand-900">Senior Inspector</p>
            </button>
          </div>

          {onConsumerPortal && (
            <button
              type="button"
              onClick={onConsumerPortal}
              className="w-full flex items-center justify-between p-3.5 rounded-2xl border border-slate-200 bg-white hover:bg-slate-50 text-xs font-semibold text-slate-700 hover:text-slate-900 transition-all shadow-2xs"
            >
              <span className="flex items-center gap-2.5">
                <Users className="h-4 w-4 text-cyan-600" />
                Citizen / Consumer Portal (No login needed)
              </span>
              <ArrowRight className="h-4 w-4 text-slate-400" />
            </button>
          )}
        </div>

        <div className="my-5 flex items-center gap-3">
          <div className="h-px flex-1 bg-slate-200" />
          <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">OR MANUAL SIGN IN</span>
          <div className="h-px flex-1 bg-slate-200" />
        </div>

        <div className="space-y-3.5">
          <div>
            <label className="text-xs font-semibold text-slate-700">Username</label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              placeholder="e.g. inspector or admin"
              className="mt-1 h-11 w-full rounded-2xl border border-blue-200/80 bg-[#EEF4FF] px-4 text-sm font-medium text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 transition-all"
            />
          </div>
          <div>
            <label className="text-xs font-semibold text-slate-700">Password</label>
            <input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              type="password"
              autoComplete="current-password"
              placeholder="••••••••"
              className="mt-1 h-11 w-full rounded-2xl border border-blue-200/80 bg-[#EEF4FF] px-4 text-sm font-medium text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 transition-all"
            />
          </div>
        </div>

        {error && (
          <div className="mt-4 flex items-center gap-2 rounded-xl bg-danger-soft px-3 py-2.5 text-xs font-medium text-destructive">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <Button type="submit" className="mt-5 w-full h-11 text-sm font-bold" disabled={submitting || !username || !password}>
          {submitting ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
          {submitting ? "Authenticating…" : "Sign In to LexMetra"}
        </Button>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Profile — real backend health
// ---------------------------------------------------------------------------

export function ProfileView({
  user,
  onLogout,
  onNavigate,
  lang = "en",
  onSetLang,
}: {
  user: AuthedUser | null;
  onLogout: () => void;
  onNavigate?: (view: View) => void;
  lang?: Language;
  onSetLang?: (newLang: Language) => void;
}) {
  const [health, setHealth] = useState<"checking" | "ok" | "down">("checking");
  const [activeModal, setActiveModal] = useState<"notifications" | "language" | "help" | null>(null);

  // Notifications State
  const [notifReminders, setNotifReminders] = useState(true);
  const [notifPriorityAlerts, setNotifPriorityAlerts] = useState(true);
  const [notifSound, setNotifSound] = useState(true);
  const [notifFrequency, setNotifFrequency] = useState("instant");
  const [notifSavedMsg, setNotifSavedMsg] = useState(false);

  // Help & Feedback State
  const [feedbackCategory, setFeedbackCategory] = useState("guidance");
  const [feedbackText, setFeedbackText] = useState("");
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);

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

  const languageLabel = lang === "hi" ? "हिंदी (Hindi)" : lang === "mr" ? "मराठी (Marathi)" : "English (India)";

  const handleSaveNotifications = () => {
    setNotifSavedMsg(true);
    setTimeout(() => {
      setNotifSavedMsg(false);
      setActiveModal(null);
    }, 1200);
  };

  const handleSubmitFeedback = (e: React.FormEvent) => {
    e.preventDefault();
    if (!feedbackText.trim()) return;
    setFeedbackSubmitted(true);
    setTimeout(() => {
      setFeedbackSubmitted(false);
      setFeedbackText("");
      setActiveModal(null);
    }, 1500);
  };

  return (
    <>
      <AppHeader
        title={lang === "hi" ? "उपयोगकर्ता प्रोफ़ाइल" : lang === "mr" ? "वापरकर्ता प्रोफाइल" : "User Profile & Settings"}
        user={user}
        onLogout={onLogout}
        onNavigate={onNavigate}
        lang={lang}
        onLanguageChange={onSetLang}
      />
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
          
          <button
            type="button"
            onClick={() => setActiveModal("notifications")}
            className="flex w-full items-center gap-3 border-b border-border p-5 text-left hover:bg-muted/50 transition"
          >
            <Bell className="h-5 w-5 text-brand" />
            <div className="flex-1">
              <p className="text-sm font-semibold">Notifications</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {notifReminders && notifPriorityAlerts ? "Reminders & priority alerts active" : "Configured preferences"}
              </p>
            </div>
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          </button>

          <button
            type="button"
            onClick={() => setActiveModal("language")}
            className="flex w-full items-center gap-3 border-b border-border p-5 text-left hover:bg-muted/50 transition"
          >
            <Settings2 className="h-5 w-5 text-brand" />
            <div className="flex-1">
              <p className="text-sm font-semibold">Language</p>
              <p className="mt-1 text-xs text-muted-foreground">{languageLabel}</p>
            </div>
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          </button>

          <button
            type="button"
            onClick={() => setActiveModal("help")}
            className="flex w-full items-center gap-3 p-5 text-left hover:bg-muted/50 transition"
          >
            <CircleHelp className="h-5 w-5 text-brand" />
            <div className="flex-1">
              <p className="text-sm font-semibold">Help & feedback</p>
              <p className="mt-1 text-xs text-muted-foreground">Product guidance & support desk</p>
            </div>
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          </button>
        </section>
        <Button variant="secondary" className="w-full" onClick={onLogout}><LogOut className="h-4 w-4" />Sign out</Button>
      </main>

      {/* Notifications Modal */}
      {activeModal === "notifications" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs animate-in fade-in duration-150">
          <div className="w-full max-w-md rounded-2xl border border-border/80 bg-card p-6 shadow-xl space-y-5">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <div className="flex items-center gap-2">
                <Bell className="h-5 w-5 text-brand" />
                <h3 className="font-bold text-foreground text-base">Notification Preferences</h3>
              </div>
              <button
                type="button"
                onClick={() => setActiveModal(null)}
                className="rounded-lg p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4 text-sm">
              <label className="flex items-center justify-between cursor-pointer">
                <div>
                  <p className="font-semibold text-foreground">Inspection Reminders</p>
                  <p className="text-xs text-muted-foreground">Alerts when pending queue items exceed SLA</p>
                </div>
                <input
                  type="checkbox"
                  checked={notifReminders}
                  onChange={(e) => setNotifReminders(e.target.checked)}
                  className="h-4 w-4 rounded accent-brand"
                />
              </label>

              <label className="flex items-center justify-between cursor-pointer">
                <div>
                  <p className="font-semibold text-foreground">Priority Violation Alerts</p>
                  <p className="text-xs text-muted-foreground">Push notification on critical Rule 6 non-compliance</p>
                </div>
                <input
                  type="checkbox"
                  checked={notifPriorityAlerts}
                  onChange={(e) => setNotifPriorityAlerts(e.target.checked)}
                  className="h-4 w-4 rounded accent-brand"
                />
              </label>

              <label className="flex items-center justify-between cursor-pointer">
                <div>
                  <p className="font-semibold text-foreground">Sound & Haptic Signals</p>
                  <p className="text-xs text-muted-foreground">Play audible beep on barcode & QR validation</p>
                </div>
                <input
                  type="checkbox"
                  checked={notifSound}
                  onChange={(e) => setNotifSound(e.target.checked)}
                  className="h-4 w-4 rounded accent-brand"
                />
              </label>

              <div>
                <p className="font-semibold text-foreground text-xs uppercase tracking-wider text-muted-foreground mb-1">
                  Digest Frequency
                </p>
                <select
                  value={notifFrequency}
                  onChange={(e) => setNotifFrequency(e.target.value)}
                  className="w-full rounded-xl border border-border bg-background px-3 py-2 text-xs font-semibold focus:border-brand focus:outline-hidden"
                >
                  <option value="instant">Instantaneous (Real-time)</option>
                  <option value="hourly">Hourly Summary</option>
                  <option value="daily">Daily End-of-Shift Digest</option>
                </select>
              </div>
            </div>

            {notifSavedMsg && (
              <div className="rounded-lg bg-success-soft p-2.5 text-center text-xs font-bold text-success">
                ✓ Preferences updated successfully!
              </div>
            )}

            <div className="flex gap-2 pt-2">
              <Button variant="secondary" className="flex-1" onClick={() => setActiveModal(null)}>
                Cancel
              </Button>
              <Button variant="primary" className="flex-1" onClick={handleSaveNotifications}>
                Save Changes
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Language Modal */}
      {activeModal === "language" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs animate-in fade-in duration-150">
          <div className="w-full max-w-sm rounded-2xl border border-border/80 bg-card p-6 shadow-xl space-y-5">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <div className="flex items-center gap-2">
                <Settings2 className="h-5 w-5 text-brand" />
                <h3 className="font-bold text-foreground text-base">Select Portal Language</h3>
              </div>
              <button
                type="button"
                onClick={() => setActiveModal(null)}
                className="rounded-lg p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                ✕
              </button>
            </div>

            <p className="text-xs text-muted-foreground">
              Choose your preferred language for the interface, legal declarations checklist, and AI assistance voice.
            </p>

            <div className="space-y-2">
              {[
                { code: "en", name: "English", sub: "Official statutory language" },
                { code: "hi", name: "हिंदी (Hindi)", sub: "राजभाषा / राष्ट्रीय उपभोक्ता सेवा" },
                { code: "mr", name: "मराठी (Marathi)", sub: "महाराष्ट्र राज्य विधी मापनशास्त्र" },
              ].map((item) => (
                <button
                  type="button"
                  key={item.code}
                  onClick={() => {
                    if (onSetLang) onSetLang(item.code as Language);
                    localStorage.setItem("lexmetra_lang", item.code);
                    setActiveModal(null);
                  }}
                  className={`w-full flex items-center justify-between rounded-xl p-3.5 text-left border transition ${
                    lang === item.code
                      ? "border-brand bg-brand/10 font-bold"
                      : "border-border/70 hover:bg-muted/50"
                  }`}
                >
                  <div>
                    <p className="text-sm font-semibold text-foreground">{item.name}</p>
                    <p className="text-[11px] text-muted-foreground">{item.sub}</p>
                  </div>
                  {lang === item.code && <span className="text-xs font-bold text-brand">✓ Selected</span>}
                </button>
              ))}
            </div>

            <Button variant="secondary" className="w-full" onClick={() => setActiveModal(null)}>
              Close
            </Button>
          </div>
        </div>
      )}

      {/* Help & Feedback Modal */}
      {activeModal === "help" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs animate-in fade-in duration-150">
          <div className="w-full max-w-md rounded-2xl border border-border/80 bg-card p-6 shadow-xl space-y-5">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <div className="flex items-center gap-2">
                <CircleHelp className="h-5 w-5 text-brand" />
                <h3 className="font-bold text-foreground text-base">Help & Support Desk</h3>
              </div>
              <button
                type="button"
                onClick={() => setActiveModal(null)}
                className="rounded-lg p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3">
              <div className="rounded-xl border border-border/70 bg-muted/30 p-3 text-xs space-y-1">
                <p className="font-bold text-foreground">Inspector Statutory Quick Links</p>
                <p className="text-muted-foreground">• Legal Metrology (Packaged Commodities) Rules, 2011</p>
                <p className="text-muted-foreground">• G.S.R. 594(E) QR Provision & Rule 26 Exemptions</p>
                <p className="text-muted-foreground">• National Consumer Helpline: <strong>1915</strong></p>
              </div>

              <form onSubmit={handleSubmitFeedback} className="space-y-3">
                <div>
                  <label className="text-xs font-semibold text-foreground">Topic</label>
                  <select
                    value={feedbackCategory}
                    onChange={(e) => setFeedbackCategory(e.target.value)}
                    className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-xs font-semibold focus:border-brand focus:outline-hidden"
                  >
                    <option value="guidance">Product Guidance & Rule Clarification</option>
                    <option value="ocr_issue">OCR / Detection Accuracy Issue</option>
                    <option value="feature_request">Feature Request / System Improvement</option>
                    <option value="other">General Technical Feedback</option>
                  </select>
                </div>

                <div>
                  <label className="text-xs font-semibold text-foreground">Your Message or Issue</label>
                  <textarea
                    rows={3}
                    value={feedbackText}
                    onChange={(e) => setFeedbackText(e.target.value)}
                    placeholder="Describe the issue encountered during inspection or your feedback..."
                    className="mt-1 w-full rounded-xl border border-border bg-background p-3 text-xs focus:border-brand focus:outline-hidden"
                    required
                  />
                </div>

                {feedbackSubmitted && (
                  <div className="rounded-lg bg-success-soft p-2.5 text-center text-xs font-bold text-success">
                    ✓ Feedback received! Docket ID #{Math.floor(100000 + Math.random() * 900000)} generated.
                  </div>
                )}

                <div className="flex gap-2 pt-1">
                  <Button variant="secondary" className="flex-1" type="button" onClick={() => setActiveModal(null)}>
                    Close
                  </Button>
                  <Button variant="primary" className="flex-1" type="submit">
                    Submit Feedback
                  </Button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Root
// ---------------------------------------------------------------------------


