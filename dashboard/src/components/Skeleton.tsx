import { clsx } from "clsx";

type SkeletonProps = {
  className?: string;
};

export const Skeleton = ({ className }: SkeletonProps) => (
  <div className={clsx("animate-pulse rounded-lg bg-foreground/10", className)} />
);
