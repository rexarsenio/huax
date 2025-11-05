import { NavLink, Outlet } from "react-router-dom";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { ThemeToggle } from "../components/ThemeToggle";
import { StatusBanner } from "../components/StatusBanner";
import { LanguageSwitcher } from "../components/LanguageSwitcher";
import huaxLogo from "../assets/landing/huaxlogo.png";

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  clsx(
    "relative px-5 py-2.5 rounded-lg text-sm font-semibold transition-all duration-200",
    isActive
      ? "bg-accent/15 text-accent shadow-sm ring-1 ring-accent/20"
      : "text-foreground-muted hover:text-foreground hover:bg-background-elevated/80 hover:shadow-sm"
  );

export const Shell = () => {
  const { t } = useTranslation();
  const footer = t("app.footer", { year: new Date().getFullYear() });

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col">
      {/* Modern Corporate Header */}
      <header className="border-b border-border/50 bg-background-secondary/95 backdrop-blur-sm sticky top-0 z-50 shadow-lg">
        <div className="max-w-7xl mx-auto flex items-center justify-between px-8 py-4 gap-8">
          {/* Logo & Brand */}
          <div className="flex items-center gap-4">
            <img
              src={huaxLogo}
              alt="Huax"
              className="h-12 w-auto opacity-90 hover:opacity-100 transition-opacity"
            />
            <div>
              <h1 className="text-xl font-bold text-foreground tracking-tight">
                {t("app.title")}
              </h1>
              <p className="text-xs text-foreground-muted font-medium">
                {t("app.subtitle")}
              </p>
            </div>
          </div>

          {/* Navigation & Actions */}
          <div className="flex items-center gap-4">
            <nav className="flex items-center gap-2">
              <NavLink to="/app" className={navLinkClass} end>
                <span className="flex items-center gap-2">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                  {t("nav.overview")}
                </span>
              </NavLink>
              <NavLink to="/app/map" className={navLinkClass}>
                <span className="flex items-center gap-2">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
                  </svg>
                  {t("nav.map", { defaultValue: "Map" })}
                </span>
              </NavLink>
              <NavLink to="/app/operations" className={navLinkClass}>
                <span className="flex items-center gap-2">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                  {t("nav.operations")}
                </span>
              </NavLink>
            </nav>

            <div className="h-6 w-px bg-border"></div>

            <div className="flex items-center gap-2">
              <LanguageSwitcher />
              <ThemeToggle />
            </div>
          </div>
        </div>
      </header>

      <StatusBanner />

      {/* Main Content */}
      <main className="flex-1 bg-background">
        <div className="max-w-[1800px] mx-auto px-8 py-10">
          <Outlet />
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-border/30 bg-background-secondary/80 py-8 text-center">
        <div className="max-w-7xl mx-auto px-8">
          <p className="text-sm text-foreground-muted font-medium">{footer}</p>
        </div>
      </footer>
    </div>
  );
};
