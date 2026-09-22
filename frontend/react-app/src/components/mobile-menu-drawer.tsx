import React, { useEffect } from "react";
import {
  X,
  Sparkles,
  LayoutDashboard,
  Camera,
  History as HistoryIcon,
  ClipboardCheck,
  ShieldAlert,
  Globe,
  FileText,
  ShieldCheck,
  Users,
  UserRound,
  Lock,
  LogOut,
  ChevronRight,
  Shield,
  FileCheck,
} from "lucide-react";
import { type Language } from "@/lib/i18n";
import { type AppView } from "@/lib/nav-history";
import { type AuthedUser } from "@/lib/api-client";

interface MobileMenuDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  currentView: AppView | string;
  onNavigate: (view: AppView | string) => void;
  lang?: Language;
  onLanguageChange?: (l: Language) => void;
  user?: AuthedUser | null;
  onLogout?: () => void;
}

export function MobileMenuDrawer({
  isOpen,
  onClose,
  currentView,
  onNavigate,
  lang = "en",
  onLanguageChange,
  user,
  onLogout,
}: MobileMenuDrawerProps) {
  // Lock body scroll when drawer is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === "Escape") onClose();
      };
      window.addEventListener("keydown", handleKeyDown);
      return () => {
        document.body.style.overflow = "";
        window.removeEventListener("keydown", handleKeyDown);
      };
    }
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const isCitizen = !user || user.role === "customer" || user.role === "consumer";

  const navItems = [
    { id: "landing", label: lang === "hi" ? "मुख्य अवलोकन" : lang === "mr" ? "मुख्य पृष्ठ" : "Platform Overview", icon: Sparkles, badge: "National" },
    { id: "scan", label: lang === "hi" ? "पैकेज स्कैन करें" : lang === "mr" ? "पॅकेज स्कॅन करा" : "Scan Package", icon: Camera, primary: true },
    ...(!isCitizen
      ? [
          { id: "home", label: lang === "hi" ? "निरीक्षक डैशबोर्ड" : lang === "mr" ? "निरीक्षक डॅशबोर्ड" : "Inspector Dashboard", icon: LayoutDashboard },
          { id: "history", label: lang === "hi" ? "निरीक्षण इतिहास" : lang === "mr" ? "तपासणी इतिहास" : "Inspection Records", icon: HistoryIcon },
          { id: "register", label: lang === "hi" ? "वैधानिक रजिस्टर" : lang === "mr" ? "वैधानिक नोंदवही" : "Statutory Register", icon: ClipboardCheck },
          { id: "reviewQueue", label: lang === "hi" ? "समीक्षा कतार" : lang === "mr" ? "पुनरावलोकन रांग" : "Review Queue", icon: ShieldAlert },
          { id: "seniorRegional", label: lang === "hi" ? "क्षेत्रीय आसूचना" : lang === "mr" ? "प्रादेशिक गुप्तचर" : "Senior Intel Heatmap", icon: Globe },
          { id: "authority", label: lang === "hi" ? "प्राधिकारी डॉकेट" : lang === "mr" ? "प्राधिकरण डॉकेट" : "Authority Action Dockets", icon: ShieldCheck },
        ]
      : []),
    { id: "customer", label: lang === "hi" ? "नागरिक उपभोक्ता पोर्टल" : lang === "mr" ? "नागरिक ग्राहक पोर्टल" : "Citizen Grievance (1915)", icon: Users },
    { id: "regulatory", label: lang === "hi" ? "विधिक नियम एवं गजट" : lang === "mr" ? "वैधानिक नियम व राजपत्र" : "Regulatory Rules & Gazette", icon: FileText },
    { id: "privacy", label: lang === "hi" ? "गोपनीयता नीति" : lang === "mr" ? "गोपनीयता धोरण" : "Privacy Policy", icon: Shield },
    { id: "terms", label: lang === "hi" ? "सेवा शर्तें" : lang === "mr" ? "सेवा अटी" : "Terms & Conditions", icon: FileCheck },
  ];

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Mobile Navigation Menu"
      className="fixed inset-0 z-50 flex justify-end md:hidden"
    >
      {/* Dimmed Backdrop */}
      <div
        className="fixed inset-0 bg-brand-950/70 backdrop-blur-xs transition-opacity animate-in fade-in duration-200"
        onClick={onClose}
      />

      {/* Slide-out Drawer */}
      <div className="relative w-[85%] max-w-sm h-full bg-white text-slate-900 shadow-2xl flex flex-col justify-between overflow-hidden z-10 animate-in slide-in-from-right duration-250 border-l border-slate-200">
        {/* Top National Stripe */}
        <div className="h-1.5 w-full tricolor-stripe shrink-0" />

        {/* Drawer Header */}
        <div className="px-4 py-3.5 border-b border-slate-100 flex items-center justify-between bg-gradient-to-r from-brand-950 via-brand-900 to-brand-850 text-white shrink-0">
          <div className="flex items-center gap-2.5">
            <img
              src="/lexmetra-white-logo.png"
              alt="LexMetra Logo"
              className="h-8 w-auto object-contain"
            />
            <div>
              <span className="text-base font-black tracking-wider text-white font-mono leading-none block">
                LEXMETRA
              </span>
              <span className="text-[10px] font-semibold text-saffron-300 leading-tight block mt-0.5">
                Statutory Legal Metrology
              </span>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Close menu"
            className="rounded-xl p-1.5 text-brand-200 hover:text-white hover:bg-white/10 transition active:scale-95 touch-manipulation cursor-pointer"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* User Info Bar */}
        {user ? (
          <div className="px-4 py-2.5 bg-slate-50 border-b border-slate-100 flex items-center justify-between shrink-0 text-xs">
            <div className="flex items-center gap-2">
              <div className="h-7 w-7 rounded-lg bg-brand-100 text-brand-800 flex items-center justify-center font-bold">
                <UserRound className="h-4 w-4" />
              </div>
              <div className="truncate">
                <p className="font-bold text-slate-900 truncate">{user.username}</p>
                <p className="text-[10px] text-slate-500 capitalize">{user.role}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => {
                onClose();
                onLogout?.();
              }}
              className="inline-flex items-center gap-1 text-[11px] font-bold text-red-600 hover:text-red-700 p-1"
            >
              <LogOut className="h-3.5 w-3.5" />
              <span>Sign Out</span>
            </button>
          </div>
        ) : null}

        {/* Drawer Scrollable Navigation Links */}
        <div className="flex-1 overflow-y-auto px-3 py-3 space-y-1">
          {navItems.map((item) => {
            const isActive = currentView === item.id;
            const Icon = item.icon;

            return (
              <button
                key={item.id}
                type="button"
                onClick={() => {
                  onNavigate(item.id as AppView);
                  onClose();
                }}
                className={`flex w-full items-center justify-between px-3 py-2.5 rounded-xl text-xs font-bold transition-all touch-manipulation cursor-pointer ${
                  item.primary
                    ? "bg-gradient-to-r from-saffron-500 via-saffron-600 to-orange-600 text-white shadow-md"
                    : isActive
                    ? "bg-brand-50 text-brand-900 border border-brand-200 shadow-xs"
                    : "text-slate-700 hover:bg-slate-100"
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <Icon
                    className={`h-4 w-4 ${
                      item.primary
                        ? "text-white"
                        : isActive
                        ? "text-brand-700"
                        : "text-slate-500"
                    }`}
                  />
                  <span>{item.label}</span>
                </div>

                <div className="flex items-center gap-1.5">
                  {item.badge && (
                    <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-brand-100 text-brand-800 uppercase">
                      {item.badge}
                    </span>
                  )}
                  <ChevronRight
                    className={`h-3.5 w-3.5 ${
                      item.primary ? "text-white/80" : "text-slate-400"
                    }`}
                  />
                </div>
              </button>
            );
          })}
        </div>

        {/* Bottom Drawer Actions: Language Selector & Sign In */}
        <div className="p-3 border-t border-slate-100 bg-slate-50/90 space-y-2.5 shrink-0">
          {/* Language Switcher */}
          {onLanguageChange && (
            <div className="flex items-center justify-between bg-white rounded-xl p-1 border border-slate-200 text-xs">
              <span className="text-[11px] font-bold text-slate-500 pl-2 flex items-center gap-1">
                <Globe className="h-3 w-3 text-saffron-600" />
                Lang
              </span>
              <div className="flex gap-1">
                {[
                  { code: "en", label: "EN" },
                  { code: "hi", label: "हिन्दी" },
                  { code: "mr", label: "मराठी" },
                ].map((l) => (
                  <button
                    key={l.code}
                    type="button"
                    onClick={() => onLanguageChange(l.code as Language)}
                    className={`px-2 py-1 rounded-lg text-[10px] font-bold transition ${
                      lang === l.code
                        ? "bg-brand-900 text-white shadow-xs"
                        : "text-slate-600 hover:bg-slate-100"
                    }`}
                  >
                    {l.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {!user ? (
            <button
              type="button"
              onClick={() => {
                onNavigate("login");
                onClose();
              }}
              className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-gradient-to-r from-purple-700 to-indigo-800 hover:from-purple-800 hover:to-indigo-900 text-white text-xs font-bold shadow-md transition active:scale-98 touch-manipulation cursor-pointer"
            >
              <Lock className="h-3.5 w-3.5" />
              <span>Officer Sign In</span>
            </button>
          ) : null}

          <p className="text-[10px] text-center text-slate-400 font-mono">
            LexMetra LMPC Platform · Rule 12 USP Engine
          </p>
        </div>
      </div>
    </div>
  );
}
