import { useState } from "react";

import huaxLogo from "../assets/landing/huaxlogo.png";
import shipImage from "../assets/landing/shipimage.png";

type Lang = "de" | "en";

type Section = {
  title: string;
  body: string[];
};

const dictionary: Record<
  Lang,
  {
    heading: string;
    intro: string;
    sections: Section[];
    footer: string[];
  }
> = {
  de: {
    heading: "Datenschutzerklärung (Landing Page)",
    intro:
      "Wir freuen uns über Ihr Interesse an HUAX. Nachfolgend informieren wir Sie darüber, wie wir personenbezogene Daten im Zusammenhang mit dieser Wartelisten-Seite verarbeiten.",
    sections: [
      {
        title: "1. Verantwortliche Stelle",
        body: [
          "HUAX · Lazzaro One UG (haftungsbeschränkt)",
          "Forckenbeckstraße 63c, 14199 Berlin, Germany",
          "Managing Director: Arsenio Longo",
          "E-Mail: office@lazzaro.one · Telefon: +49 (0)30 24618457",
        ],
      },
      {
        title: "2. Welche Daten verarbeiten wir?",
        body: [
          "Wenn Sie sich über das Formular auf dieser Seite in die Warteliste eintragen, verarbeiten wir ausschließlich die von Ihnen angegebene E-Mail-Adresse.",
          "Bei rein informatorischer Nutzung der Seite werden keine personenbezogenen Cookies oder Tracking-Technologien eingesetzt.",
        ],
      },
      {
        title: "3. Zweck und Rechtsgrundlage",
        body: [
          "Ihre E-Mail-Adresse nutzen wir, um Sie über HUAX und den Start unserer Produkte zu informieren (Art. 6 Abs. 1 lit. a DSGVO – Einwilligung).",
          "Sie können Ihre Einwilligung jederzeit per E-Mail an office@lazzaro.one widerrufen.",
        ],
      },
      {
        title: "4. Speicherdauer",
        body: [
          "Wir speichern Ihre E-Mail-Adresse so lange, bis Sie Ihre Einwilligung widerrufen oder wir den Zweck (Information über den Produktstart) erreicht haben.",
          "Nach Widerruf oder Zweckfortfall löschen wir Ihre Daten aus unserer Warteliste.",
        ],
      },
      {
        title: "5. Empfänger / Weitergabe",
        body: [
          "Eine Weitergabe Ihrer E-Mail-Adresse an Dritte findet nicht statt.",
          "Die Daten werden ausschließlich auf unseren eigenen Systemen innerhalb der EU verarbeitet.",
        ],
      },
      {
        title: "6. Ihre Rechte",
        body: [
          "Sie haben das Recht auf Auskunft, Berichtigung, Löschung, Einschränkung der Verarbeitung, Datenübertragbarkeit sowie das Recht auf Beschwerde bei einer Aufsichtsbehörde.",
          "Wenden Sie sich zur Ausübung Ihrer Rechte jederzeit an office@lazzaro.one.",
        ],
      },
      {
        title: "7. Hosting & Logfiles",
        body: [
          "Beim Aufruf der Landing-Page werden aus technischen Gründen Server-Logfiles (u. a. IP-Adresse, Datum/Uhrzeit, Browsertyp) verarbeitet. Diese Daten dienen ausschließlich der Sicherstellung des technischen Betriebs und werden nach 30 Tagen automatisch gelöscht.",
        ],
      },
      {
        title: "8. Änderungen",
        body: [
          "Wir passen diese Datenschutzhinweise an, sobald Änderungen an unseren Prozessen dies erforderlich machen. Den aktuellen Stand finden Sie auf dieser Seite.",
          "Stand: Oktober 2025",
        ],
      },
    ],
    footer: [
      "HUAX · Lazzaro One UG (haftungsbeschränkt)",
      "Forckenbeckstraße 63c · 14199 Berlin",
      "E-Mail: office@lazzaro.one",
    ],
  },
  en: {
    heading: "Privacy Notice (Landing Page)",
    intro:
      "Thank you for your interest in HUAX. Below we outline how we process personal data in connection with this waitlist landing page.",
    sections: [
      {
        title: "1. Data Controller",
        body: [
          "HUAX · Lazzaro One UG (haftungsbeschränkt)",
          "Forckenbeckstraße 63c, 14199 Berlin, Germany",
          "Managing Director: Arsenio Longo",
          "Email: office@lazzaro.one · Phone: +49 (0)30 24618457",
        ],
      },
      {
        title: "2. What Data Do We Process?",
        body: [
          "When you join the waitlist via the form on this site, we only process the email address you provide.",
          "When you merely browse the page, we do not set any personal cookies or tracking technologies.",
        ],
      },
      {
        title: "3. Purpose and Legal Basis",
        body: [
          "We use your email address to inform you about HUAX and the launch of our products (Art. 6(1)(a) GDPR – consent).",
          "You may withdraw your consent at any time by emailing office@lazzaro.one.",
        ],
      },
      {
        title: "4. Storage Period",
        body: [
          "We store your email address until you withdraw your consent or we fulfil the purpose (updates about our launch).",
          "Once the purpose no longer applies or you opt out, we remove your entry from our waitlist.",
        ],
      },
      {
        title: "5. Recipients",
        body: [
          "We do not share your email address with third parties.",
          "All data is processed exclusively on our own systems within the EU.",
        ],
      },
      {
        title: "6. Your Rights",
        body: [
          "You have the right to access, rectify, delete, restrict processing, and data portability as well as the right to lodge a complaint with a supervisory authority.",
          "To exercise these rights, contact us anytime at office@lazzaro.one.",
        ],
      },
      {
        title: "7. Hosting & Log Files",
        body: [
          "For technical reasons, server log files (e.g., IP address, date/time, browser type) are processed when you visit this page. The logs are solely used to ensure technical operations and are automatically deleted after 30 days.",
        ],
      },
      {
        title: "8. Updates",
        body: [
          "We will update this privacy notice whenever our processes change. The current version is always available here.",
          "Last updated: October 2025",
        ],
      },
    ],
    footer: [
      "HUAX · Lazzaro One UG (haftungsbeschränkt)",
      "Forckenbeckstraße 63c · 14199 Berlin · Germany",
      "Email: office@lazzaro.one",
    ],
  },
};

export const PrivacyPolicyPage = () => {
  const [lang, setLang] = useState<Lang>("de");
  const copy = dictionary[lang];

  return (
    <main className="relative min-h-screen bg-white text-gray-900">
      <div className="pointer-events-none absolute bottom-8 right-5 hidden w-28 opacity-60 md:block">
        <img src={shipImage} alt="" />
      </div>
      <div className="bg-gradient-to-b from-white via-white to-[#0b1d3a]/10 py-10">
        <div className="relative mx-auto max-w-3xl rounded-[32px] border border-white/40 bg-white/95 px-5 py-16 text-[#10254d] shadow-[0_25px_70px_rgba(11,29,58,0.12)] md:py-20">
          <div className="flex flex-col items-center gap-4 text-center">
            <div className="rounded-full border border-white/40 bg-white/95 px-6 py-4 shadow-[0_10px_30px_rgba(11,29,58,0.12)]">
              <img src={huaxLogo} alt="HUAX Logo" className="w-28 md:w-36" />
            </div>
            <div className="flex gap-2 rounded-full border border-[#0b1d3a]/20 bg-white/70 p-1 text-xs uppercase tracking-[0.2em] text-[#0b1d3a] backdrop-blur">
              <button
                type="button"
                className={`rounded-full px-4 py-1 transition ${
                  lang === "de" ? "bg-[#0b1d3a] text-white" : "hover:bg-[#0b1d3a]/10"
                }`}
                onClick={() => setLang("de")}
              >
                DE
              </button>
              <button
                type="button"
                className={`rounded-full px-4 py-1 transition ${
                  lang === "en" ? "bg-[#0b1d3a] text-white" : "hover:bg-[#0b1d3a]/10"
                }`}
                onClick={() => setLang("en")}
              >
                EN
              </button>
            </div>
          </div>

          <h1 className="mt-8 text-3xl font-semibold tracking-tight text-[#0b1d3a] md:text-4xl">
            {copy.heading}
          </h1>
          <p className="mt-4 leading-relaxed text-[#1a335f]">{copy.intro}</p>

          {copy.sections.map((section) => (
            <section className="mt-10" key={`${lang}-${section.title}`}>
              <h2 className="text-xl font-semibold text-[#0b1d3a]">{section.title}</h2>
              {section.body.map((text) => (
                <p className="mt-3 leading-relaxed" key={text}>
                  {text}
                </p>
              ))}
            </section>
          ))}

          <footer className="mt-14 border-t border-[#0b1d3a]/10 pt-6 text-sm text-[#10254d]">
            {copy.footer.map((line) => (
              <p key={line}>{line}</p>
            ))}
          </footer>
        </div>
      </div>
    </main>
  );
};
