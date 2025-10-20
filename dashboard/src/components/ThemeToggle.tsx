import { MoonIcon, SunIcon } from "./icons";
import { useTheme } from "../hooks/useTheme";
import { useTranslation } from "react-i18next";

export const ThemeToggle = () => {
  const { mode, toggle } = useTheme();
  const { t } = useTranslation();
  const label = mode === "dark" ? t("theme.dark") : t("theme.light");
  return (
    <button
      type="button"
      onClick={toggle}
      className="inline-flex items-center gap-2 rounded-full border border-foreground/20 px-3 py-2 text-sm hover:border-accent transition-colors"
      aria-label={label}
    >
      {mode === "dark" ? <MoonIcon className="h-4 w-4" /> : <SunIcon className="h-4 w-4" />}
      <span className="hidden md:inline">{label}</span>
    </button>
  );
};
