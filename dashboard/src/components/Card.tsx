import { ReactNode } from "react";
import { clsx } from "clsx";

type CardProps = {
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  variant?: "default" | "elevated" | "glass";
};

export const Card = ({
  title,
  subtitle,
  action,
  children,
  className,
  variant = "default",
}: CardProps) => {
  const variantStyles = {
    default:
      "bg-background-elevated border-border/60 shadow-md hover:shadow-lg hover:border-border",
    elevated:
      "bg-background-elevated border-border shadow-lg hover:shadow-xl",
    glass: "glass-effect shadow-xl border-white/10",
  };

  return (
    <section
      className={clsx(
        "rounded-xl border p-7 transition-all duration-300 animate-fade-in",
        variantStyles[variant],
        className
      )}
    >
      {(title || subtitle || action) && (
        <header className="mb-6 flex items-start justify-between gap-4 pb-5 border-b border-border/30">
          <div className="flex-1">
            {title && (
              <h2 className="text-2xl font-bold tracking-tight text-foreground mb-1">
                {title}
              </h2>
            )}
            {subtitle && (
              <p className="text-sm text-foreground-muted font-medium">
                {subtitle}
              </p>
            )}
          </div>
          {action && <div className="flex-shrink-0">{action}</div>}
        </header>
      )}
      <div className="space-y-4">{children}</div>
    </section>
  );
};
