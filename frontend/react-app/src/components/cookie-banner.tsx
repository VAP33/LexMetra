import React, { useEffect, useState } from "react";
import { Cookie, Shield, Check, X } from "lucide-react";
import { getCookieConsent, setCookieConsent, trackEvent } from "@/lib/analytics";

interface CookieBannerProps {
  onOpenPrivacy: () => void;
  lang?: "en" | "hi" | "mr";
}

export function CookieBanner({ onOpenPrivacy, lang = "en" }: CookieBannerProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const consent = getCookieConsent();
    if (!consent.decided) {
      // Delay display slightly to not interrupt initial page render
      const t = setTimeout(() => setVisible(true), 800);
      return () => clearTimeout(t);
    }
  }, []);

  if (!visible) return null;

  const t = {
    en: {
      title: "Statutory Compliance & Privacy Cookies",
      desc: "LexMetra uses essential cookies for statutory authentication and anonymous telemetry to optimize package OCR perception accuracy. We do not sell your data.",
      acceptAll: "Accept All",
      essentialOnly: "Essential Only",
      privacyPolicy: "Privacy Policy",
    },
    hi: {
      title: "वैधानिक अनुपालन एवं गोपनीयता कुकीज़",
      desc: "लेक्समेट्रा प्रमाणीकरण और ओसीआर सटीकता विश्लेषण के लिए आवश्यक कुकीज़ का उपयोग करता है। हम आपका व्यक्तिगत डेटा कभी नहीं बेचते।",
      acceptAll: "सभी स्वीकार करें",
      essentialOnly: "केवल आवश्यक",
      privacyPolicy: "गोपनीयता नीति",
    },
    mr: {
      title: "वैधानिक अनुपालन आणि गोपनीयता कुकीज",
      desc: "लेक्समेट्रा प्रमाणीकरण आणि ओसीआर अचूकतेसाठी आवश्यक कुकीज वापरते. आम्ही तुमचा डेटा विकत नाही.",
      acceptAll: "सर्व स्वीकारा",
      essentialOnly: "केवळ आवश्यक",
      privacyPolicy: "गोपनीयता धोरण",
    },
  }[lang] || {
    title: "Statutory Compliance & Privacy Cookies",
    desc: "LexMetra uses essential cookies for statutory authentication and anonymous telemetry to optimize package OCR perception accuracy. We do not sell your data.",
    acceptAll: "Accept All",
    essentialOnly: "Essential Only",
    privacyPolicy: "Privacy Policy",
  };

  const handleAcceptAll = () => {
    setCookieConsent(true, true);
    trackEvent("cookie_consent_updated", { status: "accepted_all" });
    setVisible(false);
  };

  const handleEssentialOnly = () => {
    setCookieConsent(true, false);
    trackEvent("cookie_consent_updated", { status: "essential_only" });
    setVisible(false);
  };

  return (
    <div
      role="region"
      aria-label="Cookie consent banner"
      className="fixed bottom-3 inset-x-3 sm:bottom-5 sm:right-5 sm:left-auto sm:max-w-md z-50 animate-in fade-in slide-in-from-bottom-5 duration-300"
    >
      <div className="rounded-2xl border-2 border-brand-200/80 bg-white/95 p-4 sm:p-5 shadow-2xl shadow-brand-950/20 backdrop-blur-md text-slate-800">
        <div className="flex items-start gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-saffron-50 text-saffron-600 border border-saffron-200">
            <Cookie className="h-5 w-5" />
          </div>

          <div className="flex-1 space-y-1.5">
            <div className="flex items-center justify-between">
              <h3 className="text-xs sm:text-sm font-bold text-brand-950 flex items-center gap-1.5">
                <Shield className="h-3.5 w-3.5 text-govgreen" />
                {t.title}
              </h3>
              <button
                type="button"
                onClick={handleEssentialOnly}
                className="text-slate-400 hover:text-slate-600 p-1 -mr-1"
                aria-label="Dismiss cookie banner"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <p className="text-[11px] sm:text-xs text-slate-600 leading-relaxed font-normal">
              {t.desc}
            </p>

            <div className="pt-2 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={handleAcceptAll}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-gradient-to-r from-brand-900 to-brand-800 hover:from-brand-950 hover:to-brand-900 text-white font-bold text-xs shadow-md transition active:scale-95 touch-manipulation cursor-pointer"
              >
                <Check className="h-3.5 w-3.5 text-govgreen" />
                {t.acceptAll}
              </button>

              <button
                type="button"
                onClick={handleEssentialOnly}
                className="inline-flex items-center px-3 py-2 rounded-xl border border-slate-200 bg-slate-50 hover:bg-slate-100 text-slate-700 font-semibold text-xs transition active:scale-95 touch-manipulation cursor-pointer"
              >
                {t.essentialOnly}
              </button>

              <button
                type="button"
                onClick={onOpenPrivacy}
                className="text-xs font-semibold text-saffron-600 hover:text-saffron-700 hover:underline px-1 py-1 touch-manipulation cursor-pointer"
              >
                {t.privacyPolicy}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
