import { useEffect, useRef, useState } from "react";
import {
  LoaderCircle,
  Maximize2,
  Mic,
  MicOff,
  Minimize2,
  Send,
  Sparkles,
  Volume2,
  VolumeX,
  X,
} from "lucide-react";
import {
  askAssistant,
  synthesizeSpeech,
} from "@/lib/api-client";
import { type Inspection } from "@/lib/types";


// ===========================================================================
// USP 4: Multilingual Voice/Text Assistant Widget
// ===========================================================================

function renderInlineMarkdown(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const regex = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let lastIdx = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIdx) {
      parts.push(text.slice(lastIdx, match.index));
    }
    const token = match[0];
    if (token.startsWith("**") && token.endsWith("**")) {
      parts.push(
        <strong key={match.index} className="font-bold text-slate-900">
          {token.slice(2, -2)}
        </strong>
      );
    } else if (token.startsWith("*") && token.endsWith("*")) {
      parts.push(
        <em key={match.index} className="italic text-slate-600">
          {token.slice(1, -1)}
        </em>
      );
    } else if (token.startsWith("`") && token.endsWith("`")) {
      parts.push(
        <code key={match.index} className="rounded bg-brand-50 px-1 py-0.5 font-mono text-[11px] text-brand-900 font-semibold border border-brand-200/50">
          {token.slice(1, -1)}
        </code>
      );
    }
    lastIdx = match.index + token.length;
  }
  if (lastIdx < text.length) {
    parts.push(text.slice(lastIdx));
  }
  return parts.length > 0 ? parts : [text];
}

function FormattedAssistantMessage({ content }: { content: string }) {
  if (!content) return null;
  const rawLines = content.split("\n");

  const blocks: React.ReactNode[] = [];
  let currentList: React.ReactNode[] = [];

  const flushList = () => {
    if (currentList.length > 0) {
      blocks.push(
        <div key={`list-${blocks.length}`} className="my-1.5 space-y-1">
          {currentList}
        </div>
      );
      currentList = [];
    }
  };

  rawLines.forEach((line, idx) => {
    const trimmed = line.trim();
    if (!trimmed) {
      flushList();
      return;
    }

    // Divider
    if (trimmed === "---" || trimmed === "***" || trimmed === "___") {
      flushList();
      blocks.push(<hr key={idx} className="my-2 border-slate-200" />);
      return;
    }

    // Headings: ### or ## or #
    if (trimmed.startsWith("#")) {
      flushList();
      const cleanHeading = trimmed.replace(/^#+\s*/, "");
      blocks.push(
        <div key={idx} className="mt-2.5 mb-1 flex items-center gap-1.5 font-bold text-xs text-brand-950 border-b border-slate-100 pb-0.5">
          <span className="h-2 w-2 rounded-full bg-saffron-500 shrink-0" />
          <span>{renderInlineMarkdown(cleanHeading)}</span>
        </div>
      );
      return;
    }

    // Bullet point: * or -
    if (/^[\*\-]\s+/.test(trimmed)) {
      const cleanItem = trimmed.replace(/^[\*\-]\s+/, "");
      currentList.push(
        <div key={idx} className="flex items-start gap-2 text-xs leading-relaxed text-slate-800">
          <span className="h-1.5 w-1.5 rounded-full bg-brand-600 shrink-0 mt-1.5" />
          <div className="flex-1">{renderInlineMarkdown(cleanItem)}</div>
        </div>
      );
      return;
    }

    // Numbered list: 1. or 2.
    const numMatch = trimmed.match(/^(\d+)\.\s+(.*)/);
    if (numMatch) {
      flushList();
      const num = numMatch[1];
      const rest = numMatch[2];
      blocks.push(
        <div key={idx} className="my-1.5 flex items-start gap-2 text-xs leading-relaxed">
          <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-brand-100 text-[10px] font-bold text-brand-900 mt-0.5">
            {num}
          </span>
          <div className="flex-1 font-medium text-slate-900">{renderInlineMarkdown(rest)}</div>
        </div>
      );
      return;
    }

    // Normal paragraph
    flushList();
    blocks.push(
      <p key={idx} className="my-1 leading-relaxed text-xs text-slate-800">
        {renderInlineMarkdown(trimmed)}
      </p>
    );
  });

  flushList();

  return <div className="space-y-1">{blocks}</div>;
}

export function MultilingualAssistantWidget({
  currentInspection,
  lang: controlledLang,
  onLanguageChange,
}: {
  currentInspection?: Inspection;
  lang?: "en" | "hi" | "mr";
  onLanguageChange?: (l: "en" | "hi" | "mr") => void;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [internalLang, setInternalLang] = useState<"en" | "hi" | "mr">("en");
  const lang = controlledLang || internalLang;
  const setLang = (l: "en" | "hi" | "mr") => {
    setInternalLang(l);
    if (onLanguageChange) onLanguageChange(l);
  };

  const getGreeting = (l: "en" | "hi" | "mr") => {
    if (l === "hi") return "नमस्ते! मैं लेक्समेट्रा एआई हूँ, मैं आपकी क्या मदद कर सकता हूँ?";
    if (l === "mr") return "नमस्कार! मी लेक्समेट्रा एआय आहे, मी तुम्हाला कशी मदत करू शकतो?";
    return "Hello! I am LexMetra AI, How Can I Help You?";
  };

  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Array<{ role: "user" | "assistant"; text: string; sources?: string[] }>>([
    {
      role: "assistant",
      text: getGreeting(lang),
    },
  ]);
  const [showPromptCards, setShowPromptCards] = useState(true);
  const [loading, setLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isVoiceMuted, setIsVoiceMuted] = useState(false);

  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const isVoiceMutedRef = useRef(false);

  // Update greeting when language changes if only the initial greeting is present
  useEffect(() => {
    setMessages((prev) => {
      if (prev.length === 1 && prev[0].role === "assistant") {
        return [{ role: "assistant", text: getGreeting(lang) }];
      }
      return prev;
    });
  }, [lang]);

  // Sync mute state ref
  useEffect(() => {
    isVoiceMutedRef.current = isVoiceMuted;
    if (isVoiceMuted) {
      stopAllAudio();
    }
  }, [isVoiceMuted]);

  function stopAllAudio() {
    if (currentAudioRef.current) {
      try {
        currentAudioRef.current.pause();
        currentAudioRef.current.currentTime = 0;
      } catch {}
      currentAudioRef.current = null;
    }
    if (typeof window !== "undefined" && window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    setIsSpeaking(false);
  }

  // Speech Recognition support
  function toggleListening() {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Speech recognition is not supported in this browser. Please type your question.");
      return;
    }

    if (isListening) {
      setIsListening(false);
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.lang = lang === "hi" ? "hi-IN" : lang === "mr" ? "mr-IN" : "en-IN";
      recognition.continuous = false;
      recognition.interimResults = false;

      recognition.onstart = () => setIsListening(true);
      recognition.onend = () => setIsListening(false);
      recognition.onerror = () => setIsListening(false);
      recognition.onresult = (e: any) => {
        const transcript = e.results[0][0].transcript;
        if (transcript) {
          setInput(transcript);
          handleSend(transcript);
        }
      };
      recognition.start();
    } catch (e) {
      setIsListening(false);
    }
  }

  // Text-to-Speech support: Strictly Sarvam AI Bulbul v3 Indian natural voice (shubh)
  async function speakText(text: string) {
    if (!text || isVoiceMutedRef.current) return;
    stopAllAudio();
    setIsSpeaking(true);

    try {
      const audioUrl = await synthesizeSpeech(text, lang, "shubh", 1.12);
      if (audioUrl && !isVoiceMutedRef.current) {
        const audio = new Audio(audioUrl);
        currentAudioRef.current = audio;
        audio.onended = () => {
          setIsSpeaking(false);
          currentAudioRef.current = null;
        };
        audio.onerror = () => {
          setIsSpeaking(false);
          currentAudioRef.current = null;
        };
        await audio.play();
      } else {
        setIsSpeaking(false);
      }
    } catch (err) {
      console.warn("Sarvam AI speech synthesis:", err);
      setIsSpeaking(false);
    }
  }

  async function handleSend(textToSend?: string) {
    const q = (textToSend || input).trim();
    if (!q || loading) return;

    // Instantly collapse 3 floating prompt cards on selection
    setShowPromptCards(false);
    setInput("");
    setMessages((prev) => [...prev, { role: "user", text: q }]);
    setLoading(true);

    try {
      const res = await askAssistant({
        query: q,
        language: lang,
        inspection_id: currentInspection?.id,
        inspection_context: currentInspection,
      });

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: res.response_text,
          sources: res.grounding_sources,
        },
      ]);
      speakText(res.speech_text);
    } catch (e: any) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: "Sorry, I could not process your query at this moment. Please try again.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  const suggestionCards = [
    {
      titleEn: "Explain this inspection",
      subEn: "Comprehensive review of packaging compliance & facts",
      titleHi: "इस निरीक्षण को समझाएं",
      subHi: "पैकेजिंग अनुपालन एवं तथ्यों की विस्तृत समीक्षा",
      titleMr: "या तपासणीचा अहवाल समजून सांगा",
      subMr: "पॅकेजिंग कायदेशीर अनुपालन व तथ्यांचे पुनरावलोकन",
      query: "Explain this inspection and its overall findings",
    },
    {
      titleEn: "Explain package violations",
      subEn: "Analyze detected LMPC non-compliance and issues",
      titleHi: "पैकेज उल्लंघनों को समझाएं",
      subHi: "पहचाने गए LMPC गैर-अनुपालन एवं दोषों का विश्लेषण",
      titleMr: "पॅकेजवरील उल्लंघने स्पष्ट करा",
      subMr: "आढळलेले LMPC कायदेशीर नियमभंग आणि त्रुटींचे विश्लेषण",
      query: "Explain the violations found on this package",
    },
    {
      titleEn: "Statutory rules for MRP & Net Qty",
      subEn: "Rule 6(1) declarations and Rule 6(11) Unit Sale Price",
      titleHi: "MRP व शुद्ध वजन विधिक नियम",
      subHi: "नियम 6(1) घोषणाएं एवं नियम 6(11) इकाई विक्रय मूल्य",
      titleMr: "MRP व निव्वळ वजनाचे कायदेशीर नियम",
      subMr: "नियम 6(1) अनिवार्य घोषणा व नियम 6(11) युनिट विक्री किंमत",
      query: "Explain the applicable Legal Metrology rules for MRP and Net Weight",
    },
  ];

  return (
    <div className="fixed bottom-20 right-4 md:bottom-6 md:right-6 z-40">
      {!isOpen ? (
        <button
          type="button"
          onClick={() => setIsOpen(true)}
          className="flex h-14 items-center gap-2.5 rounded-full border-2 border-black bg-white px-5 text-black shadow-2xl transition-all hover:scale-105 hover:bg-black hover:text-white active:scale-95 group"
        >
          <Sparkles className="h-5 w-5 text-black group-hover:text-white transition-colors" />
          <span className="text-xs font-black uppercase tracking-wider">LexMetra AI</span>
        </button>
      ) : (
        <div
          className={`flex flex-col rounded-3xl border-2 border-slate-300/80 bg-white text-slate-900 shadow-2xl overflow-hidden transition-all duration-200 animate-in fade-in zoom-in-95 slide-in-from-bottom-6 ${
            isExpanded
              ? "h-[85vh] max-h-[840px] w-[calc(100vw-32px)] sm:w-[680px] md:w-[780px]"
              : "h-[540px] max-h-[84vh] w-[calc(100vw-32px)] sm:w-[420px]"
          }`}
        >
          {/* Header - Clean B&W LexMetra AI without any Department/Ministry */}
          <div className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3">
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-black text-white shadow-xs">
                <Sparkles className="h-4 w-4" />
              </div>
              <div>
                <p className="text-xs font-black tracking-wide text-black">LexMetra AI</p>
                <p className="text-[10px] font-medium text-slate-500">Multilingual Voice & Intelligence</p>
              </div>
            </div>
            <div className="flex items-center gap-1.5">
              {/* Voice Mute / Unmute Toggle Button */}
              <button
                type="button"
                onClick={() => setIsVoiceMuted((prev) => !prev)}
                title={isVoiceMuted ? "Unmute Voice" : "Mute Voice"}
                className={`flex items-center gap-1 px-2.5 py-1 rounded-xl text-xs font-bold border transition-all ${
                  isVoiceMuted
                    ? "bg-slate-100 text-slate-500 border-slate-300"
                    : "bg-black text-white border-black"
                }`}
              >
                {isVoiceMuted ? (
                  <>
                    <VolumeX className="h-3.5 w-3.5 text-slate-500" />
                    <span className="text-[10px]">Muted</span>
                  </>
                ) : (
                  <>
                    <Volume2 className={`h-3.5 w-3.5 text-white ${isSpeaking ? "animate-pulse" : ""}`} />
                    <span className="text-[10px]">Voice On</span>
                  </>
                )}
              </button>

              {/* Language Switcher - Black and White Pill */}
              <div className="inline-flex items-center gap-0.5 rounded-xl border border-slate-200 bg-slate-50 p-0.5 text-[10px] font-bold shadow-2xs">
                <button
                  type="button"
                  onClick={() => setLang("en")}
                  className={`px-2 py-0.5 rounded-lg transition-all ${
                    lang === "en" ? "bg-black text-white font-bold" : "text-slate-700 hover:text-black font-semibold"
                  }`}
                >
                  EN
                </button>
                <button
                  type="button"
                  onClick={() => setLang("hi")}
                  className={`px-2 py-0.5 rounded-lg transition-all ${
                    lang === "hi" ? "bg-black text-white font-bold" : "text-slate-700 hover:text-black font-semibold"
                  }`}
                >
                  हिन्दी
                </button>
                <button
                  type="button"
                  onClick={() => setLang("mr")}
                  className={`px-2 py-0.5 rounded-lg transition-all ${
                    lang === "mr" ? "bg-black text-white font-bold" : "text-slate-700 hover:text-black font-semibold"
                  }`}
                >
                  मराठी
                </button>
              </div>
              {/* Expand / Minimize Toggle Button */}
              <button
                type="button"
                onClick={() => setIsExpanded(!isExpanded)}
                title={isExpanded ? "Collapse window" : "Expand window"}
                className="rounded-lg p-1 text-slate-500 hover:bg-slate-100 hover:text-black transition-colors"
                aria-label={isExpanded ? "Collapse window" : "Expand window"}
              >
                {isExpanded ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
              </button>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="rounded-lg p-1 text-slate-500 hover:bg-slate-100 hover:text-black"
                aria-label="Close assistant"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Messages Container */}
          <div className="flex-1 space-y-3 overflow-y-auto p-4 text-xs bg-white">
            {messages.map((m, idx) => (
              <div
                key={idx}
                className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[88%] rounded-2xl p-3.5 leading-relaxed ${
                    m.role === "user"
                      ? "bg-black text-white rounded-br-xs shadow-sm font-medium"
                      : "bg-slate-50 text-slate-900 border border-slate-200/90 rounded-bl-xs shadow-xs"
                  }`}
                >
                  {m.role === "user" ? (
                    <p className="font-semibold text-white text-xs whitespace-pre-wrap">{m.text}</p>
                  ) : (
                    <FormattedAssistantMessage content={m.text} />
                  )}
                  {m.sources && m.sources.length > 0 && (
                    <div className="mt-2.5 border-t border-slate-200 pt-1.5 text-[10px] text-slate-500 font-medium">
                      <strong className="text-black font-bold">Statutory Sources:</strong> {m.sources.join(" · ")}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {/* 3 Floating Rectangular Prompt Boxes Stacked One Above Another (Claude-style) */}
            {showPromptCards && messages.length <= 1 && (
              <div className="pt-2 space-y-2 animate-in fade-in slide-in-from-bottom-2 duration-300">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 px-1">
                  {lang === "hi" ? "त्वरित सुझाव:" : lang === "mr" ? "सुचवलेले प्रश्न:" : "Quick Suggestions:"}
                </p>
                {suggestionCards.map((card, idx) => {
                  const title = lang === "hi" ? card.titleHi : lang === "mr" ? card.titleMr : card.titleEn;
                  const sub = lang === "hi" ? card.subHi : lang === "mr" ? card.subMr : card.subEn;
                  return (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => handleSend(card.query)}
                      className="w-full text-left rounded-2xl border border-slate-200 bg-slate-50/70 p-3 hover:bg-black hover:text-white hover:border-black transition-all shadow-xs group active:scale-[0.99] flex items-center justify-between gap-3"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-bold text-slate-900 group-hover:text-white transition-colors">
                          {title}
                        </p>
                        <p className="text-[10px] text-slate-500 group-hover:text-slate-300 transition-colors truncate mt-0.5">
                          {sub}
                        </p>
                      </div>
                      <span className="text-slate-400 group-hover:text-white font-bold text-sm shrink-0">→</span>
                    </button>
                  );
                })}
              </div>
            )}

            {loading && (
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <LoaderCircle className="h-3.5 w-3.5 animate-spin text-black" /> LexMetra AI processing…
              </div>
            )}
          </div>

          {/* Input Bar */}
          <div className="border-t border-slate-200 bg-white p-3">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSend();
              }}
              className="flex items-center gap-2"
            >
              <button
                type="button"
                onClick={toggleListening}
                className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border transition-all ${
                  isListening
                    ? "border-red-500 bg-red-50 text-red-600 animate-pulse"
                    : "border-slate-300 bg-white text-slate-700 hover:border-black hover:text-black"
                }`}
                title="Voice input (Mic)"
              >
                {isListening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
              </button>
              {/* Circular waveform icon button beside mic */}
              <button
                type="button"
                onClick={toggleListening}
                className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-black text-white shadow-md transition-all hover:scale-105 active:scale-95 ${
                  isListening ? "ring-2 ring-black animate-pulse" : ""
                }`}
                title="Voice Assistant Live Mode"
              >
                <span className="flex items-center justify-center gap-[2.5px]">
                  <span className={`w-[2.5px] rounded-full bg-white transition-all ${isListening || isSpeaking ? "h-3.5 animate-bounce" : "h-2"}`} />
                  <span className={`w-[2.5px] rounded-full bg-white transition-all ${isListening || isSpeaking ? "h-5 animate-pulse" : "h-3.5"}`} />
                  <span className={`w-[2.5px] rounded-full bg-white transition-all ${isListening || isSpeaking ? "h-4 animate-bounce" : "h-3"}`} />
                  <span className={`w-[2.5px] rounded-full bg-white transition-all ${isListening || isSpeaking ? "h-2.5 animate-pulse" : "h-1.5"}`} />
                </span>
              </button>
              <input
                type="text"
                placeholder={lang === "hi" ? "अपना प्रश्न पूछें..." : lang === "mr" ? "तुमचा प्रश्न विचारा..." : "Ask compliance question..."}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                className="h-9 flex-1 rounded-xl border border-slate-300 bg-slate-50 px-3 text-xs outline-none focus:border-black focus:bg-white text-slate-900 transition-colors"
              />
              <button
                type="submit"
                disabled={!input.trim() || loading}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-black text-white hover:bg-slate-800 disabled:opacity-40 transition-colors shadow-xs"
              >
                <Send className="h-4 w-4" />
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
