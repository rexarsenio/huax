import { useTranslation } from "react-i18next";
import { useHealthStatus } from "../hooks/useApi";
import { CheckIcon, WarningIcon, XIcon } from "./icons";

const statusClass = (status: string) => {
  switch (status) {
    case "ready":
      return "bg-success/20 text-success border-success/30";
    case "ok":
      return "bg-accent/10 text-accent border-accent/30";
    default:
      return "bg-danger/20 text-danger border-danger/30";
  }
};

const statusIcon = (status: string) => {
  switch (status) {
    case "ready":
      return <CheckIcon className="h-4 w-4" />;
    case "ok":
      return <WarningIcon className="h-4 w-4" />;
    default:
      return <XIcon className="h-4 w-4" />;
  }
};

export const StatusBanner = () => {
  const { data, isLoading, isError } = useHealthStatus();
  const { t } = useTranslation();

  if (isLoading) {
    return null;
  }

  const status = isError ? "not_ready" : data?.status ?? "not_ready";
  const translatedStatus = t(`status.${status}`);

  return (
    <div className={`border-y px-4 py-2 text-sm flex justify-center ${statusClass(status)}`}>
      <div className="flex items-center gap-2">
        {statusIcon(status)}
        <span className="font-medium uppercase tracking-wide">{translatedStatus}</span>
        {data?.missing && data.missing.length > 0 && (
          <span className="text-xs opacity-80">
            {t("status.missing")}: {data.missing.join(", ")}
          </span>
        )}
      </div>
    </div>
  );
};
