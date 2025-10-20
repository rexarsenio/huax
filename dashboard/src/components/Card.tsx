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
      "bg-background-elevated border-border shadow-card hover:shadow-card-hover",
    elevated:
      "bg-background-elevated border-border shadow-card-hover",
    glass: "glass-effect shadow-glow",
  };

  return (
    <section
      className={clsx(
        "rounded-2xl border p-6 transition-smooth animate-fade-in",
        variantStyles[variant],
        className
      )}
    >
      {(title || subtitle || action) && (
        <header className="mb-5 flex items-start justify-between gap-4">
          <div className="flex-1">
            {title && (
              <h2 className="text-xl font-semibold tracking-tight text-foreground">
                {title}
              </h2>
            )}
            {subtitle && (
              <p className="mt-1 text-sm text-foreground-muted">
                {subtitle}
              </p>
            )}
          </div>
          {action && <div className="flex-shrink-0">{action}</div>}
        </header>
      )}
      <div>{children}</div>
    </section>
  );
};
