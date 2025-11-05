import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import "../../i18n";
import { HeroKpi } from "../HeroKpi";

const SNAPSHOT = {
  scope: "global",
  ts: "2025-11-03T12:00:00Z",
  spvx: 49.3,
  seasonal_baseline: 126.1,
  deviation_pct: -60.9,
  zscore: -0.7,
  percentile_70d: 9,
  delta_day_points: -13.1,
  delta_day_pct: -21.0,
  classification: {
    status: "QUIET",
    severity: "watch",
    direction: "below_seasonal",
    color: "blue",
    emoji: "😌",
    headline: "Quieter than normal",
  },
};

describe("HeroKpi", () => {
  it("renders snapshot metrics", () => {
    render(<HeroKpi data={SNAPSHOT} />);

    expect(screen.getByText(/SPVX \(today\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Quieter than normal/i)).toBeInTheDocument();
    expect(screen.getAllByText(/49\.3/)).not.toHaveLength(0);
    expect(screen.getByText(/Percentile \(70d\)/i)).toBeInTheDocument();
  });

  it("shows loading skeleton", () => {
    render(<HeroKpi isLoading />);
    expect(screen.getByText(/Loading latest snapshot/i)).toBeInTheDocument();
  });

  it("shows retry placeholder on error", () => {
    const retry = vi.fn();
    render(<HeroKpi isError onRetry={retry} />);

    const unavailableMessages = screen.getAllByText(/Latest snapshot unavailable/i);
    expect(unavailableMessages.length).toBeGreaterThan(0);
    const button = screen.getByRole("button", { name: /refresh/i });
    button.click();
    expect(retry).toHaveBeenCalledTimes(1);
  });
});
