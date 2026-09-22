import React, { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  History as HistoryIcon,
  ClipboardCheck,
  ArrowLeft,
  Bell,
  Check,
  ChevronDown,
  Globe,
  LogOut,
  Menu,
  ShieldCheck,
  Sparkles,
  UserRound,
  WifiOff,
  X,
} from "lucide-react";
import { type AuthedUser, checkHealth, clearSession } from "@/lib/api-client";
import { type Language, getTranslation } from "@/lib/i18n";
import { type Inspection } from "@/lib/types";
import { type View } from "./ui-primitives";

export function Header({
  title,
  eyebrow,
  onMenu,
  online,
  lang = "en",
  onLanguageChange,
  user,
  onLogout,
  onNavigate,
}: {
  title: string;
  eyebrow?: string;
  onMenu?: () => void;
  online?: boolean;
  lang?: Language;
  onLanguageChange?: (l: Language) => void;
  user?: AuthedUser | null;
  onLogout?: () => void;
  onNavigate?: (view: View) => void;
}) {
  const [fontScale, setFontScale] = useState<"sm" | "md" | "lg">("md");
  const [isHighContrast, setIsHighContrast] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isLangOpen, setIsLangOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const langMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsMenuOpen(false);
      }
      if (langMenuRef.current && !langMenuRef.current.contains(event.target as Node)) {
        setIsLangOpen(false);
      }
    }
    if (isMenuOpen || isLangOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [isMenuOpen, isLangOpen]);

  const changeFontScale = (scale: "sm" | "md" | "lg") => {
    setFontScale(scale);
    document.documentElement.classList.remove("font-scale-sm", "font-scale-md", "font-scale-lg", "font-scale-xl");
    if (scale !== "md") {
      document.documentElement.classList.add(`font-scale-${scale}`);
    }
  };

  const toggleContrast = () => {
    const next = !isHighContrast;
    setIsHighContrast(next);
    if (next) {
      document.body.classList.add("high-contrast");
    } else {
      document.body.classList.remove("high-contrast");
    }
  };

  const defaultEyebrow =
    lang === "hi"
      ? "विधिक मापविज्ञान प्रभाग · वैधानिक अनुपालन"
      : lang === "mr"
      ? "कायदेशीर मापनशास्त्र विभाग · वैधानिक अनुपालन"
      : "STATUTORY COMPLIANCE · LEGAL METROLOGY DIVISION";

  return (
    <header className="sticky top-0 z-30 border-b border-brand-900/60 bg-gradient-to-r from-brand-950 via-brand-900 to-brand-800 text-white shadow-md">
      {/* GIGW 3.0 Skip Link */}
      <a href="#main-content" className="skip-link">
        Skip to Main Content
      </a>
      {/* DBIM National Tricolor Band */}
      <div className="h-1.5 w-full tricolor-stripe" />
      <div className="mx-auto flex min-h-[64px] sm:h-[76px] max-w-7xl items-center justify-between px-2.5 sm:px-6 lg:px-8 py-1.5 flex-wrap sm:flex-nowrap gap-1.5 sm:gap-3">
        <div className="flex items-center gap-2 sm:gap-3.5">
          <button type="button" aria-label="Open navigation" onClick={onMenu} className="rounded-lg p-1.5 text-brand-200 hover:bg-white/10 md:hidden">
            <Menu className="h-5 w-5" />
          </button>

          {/* Page title with new logo */}
          <button
            type="button"
            onClick={() => onNavigate?.("landing")}
            className="flex items-center gap-2 sm:gap-2.5 rounded-xl hover:bg-white/5 px-1.5 py-1 -mx-1.5 -my-1 transition active:scale-[0.98]"
          >
            <img
              src="/lexmetra-white-logo.png"
              alt="LexMetra"
              className="h-7 sm:h-9 w-auto object-contain shrink-0"
              draggable={false}
            />
            <h1 className="text-sm sm:text-lg font-black tracking-tight text-white line-clamp-1">
              {title}
            </h1>
          </button>
        </div>

        <div className="flex items-center gap-1 sm:gap-2 flex-wrap sm:flex-nowrap justify-end">
          {/* GIGW 3.0 Accessibility Controls: Font Resizer & High Contrast */}
          <div className="flex items-center gap-0.5 rounded-lg border border-brand-700/60 bg-brand-950/70 p-0.5 text-xs font-semibold shadow-inner">
            <button
              type="button"
              onClick={() => changeFontScale("sm")}
              title="Decrease text size (A-)"
              className={`rounded px-1.5 py-0.5 text-[9px] sm:text-[10px] font-bold transition ${fontScale === "sm" ? "bg-brand-600 text-white" : "text-brand-200 hover:text-white"}`}
            >
              A-
            </button>
            <button
              type="button"
              onClick={() => changeFontScale("md")}
              title="Normal text size (A)"
              className={`rounded px-1.5 py-0.5 text-[9px] sm:text-[10px] font-bold transition ${fontScale === "md" ? "bg-brand-600 text-white" : "text-brand-200 hover:text-white"}`}
            >
              A
            </button>
            <button
              type="button"
              onClick={() => changeFontScale("lg")}
              title="Increase text size (A+)"
              className={`rounded px-1.5 py-0.5 text-[9px] sm:text-[10px] font-bold transition ${fontScale === "lg" ? "bg-brand-600 text-white" : "text-brand-200 hover:text-white"}`}
            >
              A+
            </button>
            <div className="h-3 w-px bg-brand-700/60 mx-0.5" />
            <button
              type="button"
              onClick={toggleContrast}
              title="Toggle high contrast accessibility"
              className={`rounded px-1.5 py-0.5 text-[9px] sm:text-[10px] font-bold transition ${isHighContrast ? "bg-amber-400 text-slate-950 font-black" : "text-brand-200 hover:text-white"}`}
            >
              ◐<span className="hidden sm:inline ml-1">{isHighContrast ? "Standard" : "Contrast"}</span>
            </button>
          </div>

          {/* Global Header Language Switcher - Globe Icon Dropdown */}
          {onLanguageChange && (
            <div className="relative" ref={langMenuRef}>
              <button
                type="button"
                aria-label="Select Language"
                onClick={() => setIsLangOpen((prev) => !prev)}
                className="flex items-center gap-1.5 rounded-xl border border-white/20 bg-white/10 px-2.5 sm:px-3 py-1.5 text-xs font-bold text-white shadow-xs backdrop-blur-xs transition hover:bg-white/20 active:scale-95"
              >
                <Globe className="h-4 w-4 text-saffron-300" />
                <span className="text-xs uppercase tracking-wide">
                  {lang === "hi" ? "हिन्दी" : lang === "mr" ? "मराठी" : "EN"}
                </span>
                <ChevronDown className={`h-3 w-3 text-brand-200 transition-transform ${isLangOpen ? "rotate-180" : ""}`} />
              </button>

              {isLangOpen && (
                <div className="absolute right-0 mt-2 w-44 rounded-2xl border border-slate-200 bg-white p-1.5 text-slate-800 shadow-2xl z-50 animate-in fade-in slide-in-from-top-2 duration-150">
                  <div className="px-2.5 py-1.5 border-b border-slate-100 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                    {lang === "hi" ? "भाषा चुनें" : lang === "mr" ? "भाषा निवडा" : "Select Language"}
                  </div>
                  <div className="py-1 space-y-0.5">
                    {[
                      { code: "en", label: "English", sub: "Default" },
                      { code: "hi", label: "हिन्दी", sub: "Hindi" },
                      { code: "mr", label: "मराठी", sub: "Marathi" },
                    ].map((opt) => {
                      const isActive = lang === opt.code;
                      return (
                        <button
                          key={opt.code}
                          type="button"
                          onClick={() => {
                            onLanguageChange(opt.code as Language);
                            setIsLangOpen(false);
                          }}
                          className={`flex w-full items-center justify-between rounded-xl px-2.5 py-2 text-xs transition ${
                            isActive
                              ? "bg-purple-50 text-purple-900 font-bold"
                              : "text-slate-700 hover:bg-slate-100 font-medium"
                          }`}
                        >
                          <div className="flex flex-col text-left">
                            <span>{opt.label}</span>
                            <span className="text-[10px] text-slate-400">{opt.sub}</span>
                          </div>
                          {isActive && <Check className="h-4 w-4 text-purple-700" />}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

          {online === false && (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-destructive/20 px-2 sm:px-2.5 py-0.5 sm:py-1 text-[10px] sm:text-xs font-semibold text-red-300 border border-destructive/30">
              <WifiOff className="h-3 w-3" />Offline
            </span>
          )}

          {/* User Profile Burger Menu */}
          <div className="relative" ref={menuRef}>
            <button
              type="button"
              aria-label="User Profile & Menu"
              onClick={() => setIsMenuOpen((prev) => !prev)}
              className="flex h-8 w-8 sm:h-9 sm:w-9 items-center justify-center rounded-xl bg-white/10 text-white border border-white/20 shadow-sm hover:bg-white/20 active:scale-95 transition-all"
            >
              <UserRound className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-saffron-300" />
            </button>

            {isMenuOpen && (
              <div className="absolute right-0 mt-2.5 w-60 rounded-2xl border border-slate-200 bg-white p-2 text-slate-800 shadow-2xl z-50 animate-in fade-in slide-in-from-top-2 duration-150">
                {/* User Info Header */}
                <div className="px-3 py-2.5 border-b border-slate-100">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                    {lang === "hi" ? "लॉगिन उपयोगकर्ता" : lang === "mr" ? "लॉगिन वापरकर्ता" : "Signed in as"}
                  </p>
                  <p className="text-sm font-bold text-slate-900 truncate">{user?.username || "Authorized Officer"}</p>
                  <div className="mt-1.5 inline-flex items-center gap-1.5 rounded-md bg-amber-50 px-2 py-0.5 text-[10px] font-bold text-amber-800 border border-amber-200">
                    <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                    <span className="capitalize">{user?.role || "Inspector"}</span>
                  </div>
                </div>

                {/* Menu Items */}
                <div className="py-1 space-y-0.5">
                  <button
                    type="button"
                    onClick={() => {
                      setIsMenuOpen(false);
                      onNavigate?.("profile");
                    }}
                    className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 hover:text-black transition-colors"
                  >
                    <UserRound className="h-4 w-4 text-brand" />
                    {lang === "hi" ? "अधिकारी प्रोफ़ाइल" : lang === "mr" ? "अधिकारी प्रोफाइल" : "Officer Profile"}
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setIsMenuOpen(false);
                      onNavigate?.("history");
                    }}
                    className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 hover:text-black transition-colors"
                  >
                    <HistoryIcon className="h-4 w-4 text-slate-500" />
                    {lang === "hi" ? "निरीक्षण इतिहास" : lang === "mr" ? "तपासणी इतिहास" : "Inspection History"}
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setIsMenuOpen(false);
                      onNavigate?.("register");
                    }}
                    className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 hover:text-black transition-colors"
                  >
                    <ClipboardCheck className="h-4 w-4 text-emerald-600" />
                    {lang === "hi" ? "वैधानिक रजिस्टर" : lang === "mr" ? "वैधानिक नोंदवही" : "Statutory Register"}
                  </button>
                </div>

                {/* Sign Out / Action */}
                <div className="pt-1 mt-1 border-t border-slate-100">
                  <button
                    type="button"
                    onClick={() => {
                      setIsMenuOpen(false);
                      clearSession();
                      if (onLogout) {
                        onLogout();
                      } else if (onNavigate) {
                        onNavigate("login");
                      } else {
                        window.location.reload();
                      }
                    }}
                    className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-xs font-bold text-red-600 hover:bg-red-50 hover:text-red-700 transition-colors"
                  >
                    <LogOut className="h-4 w-4 text-red-600" />
                    {lang === "hi" ? "साइन आउट" : lang === "mr" ? "साइन आउट करा" : "Sign Out"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}

export const AppHeader = Header;


