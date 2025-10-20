import { useState, useRef, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { supportedLanguages } from "../i18n";
import { clsx } from "clsx";

const languageIcons: Record<string, string> = {
  en: "🇬🇧",
  it: "🇮🇹",
  es: "🇪🇸",
  pt: "🇵🇹",
};

const languageNames: Record<string, string> = {
  en: "English",
  it: "Italiano",
  es: "Español",
  pt: "Português",
};

export const LanguageSwitcher = () => {
  const { i18n } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const current = supportedLanguages.find((lang) => i18n.language.startsWith(lang.code))?.code ?? "en";

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleLanguageChange = (langCode: string) => {
    void i18n.changeLanguage(langCode);
    setIsOpen(false);
  };

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-2 rounded-xl bg-background-elevated border border-border hover:border-accent/50 transition-smooth"
        aria-label="Change language"
      >
        <span className="text-lg">{languageIcons[current]}</span>
        <span className="text-sm font-medium hidden sm:inline">{current.toUpperCase()}</span>
        <svg
          className={clsx("w-4 h-4 transition-transform", isOpen && "rotate-180")}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-48 rounded-xl border border-border bg-background-elevated shadow-card-hover z-50 overflow-hidden animate-fade-in">
          {supportedLanguages.map((lang) => (
            <button
              key={lang.code}
              onClick={() => handleLanguageChange(lang.code)}
              className={clsx(
                "w-full flex items-center gap-3 px-4 py-3 text-left transition-smooth",
                current === lang.code
                  ? "bg-accent/10 text-accent"
                  : "hover:bg-background-secondary text-foreground"
              )}
            >
              <span className="text-xl">{languageIcons[lang.code]}</span>
              <div className="flex-1">
                <div className="text-sm font-medium">{languageNames[lang.code]}</div>
                <div className="text-xs text-foreground-muted">{lang.code.toUpperCase()}</div>
              </div>
              {current === lang.code && (
                <svg className="w-5 h-5 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
