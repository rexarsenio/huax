import { describe, expect, it } from "vitest";
import { gaugeModel } from "./gaugeModel";

describe("gaugeModel", () => {
  it("returns no-data when baseline is invalid", () => {
    expect(gaugeModel(50, 0)).toEqual({ state: "no-data" });
    expect(gaugeModel(50, NaN)).toEqual({ state: "no-data" });
    expect(gaugeModel(undefined, 100)).toEqual({ state: "no-data" });
  });

  it("computes quiet zone below 80%", () => {
    const result = gaugeModel(40, 120);
    if (result.state !== "ok") {
      throw new Error("Expected ok state");
    }
    expect(result.zone).toBe("QUIET");
    expect(result.color).toBe("#4f46e5");
    expect(result.ratioClamped).toBeCloseTo(33.33, 2);
    expect(result.angleDeg).toBeGreaterThan(150);
  });

  it("computes normal zone around baseline", () => {
    const result = gaugeModel(120, 120);
    if (result.state !== "ok") {
      throw new Error("Expected ok state");
    }
    expect(result.zone).toBe("NORMAL");
    expect(result.color).toBe("#10b981");
    expect(result.ratioClamped).toBe(100);
    expect(result.angleDeg).toBeCloseTo(90, 3);
  });

  it("computes elevated zone between 120% and 150%", () => {
    const result = gaugeModel(160, 120);
    if (result.state !== "ok") {
      throw new Error("Expected ok state");
    }
    expect(result.zone).toBe("ELEVATED");
    expect(result.color).toBe("#f59e0b");
    expect(result.ratioClamped).toBeCloseTo(133.33, 2);
  });

  it("clamps ratios above 200% and marks hot zone", () => {
    const result = gaugeModel(300, 120);
    if (result.state !== "ok") {
      throw new Error("Expected ok state");
    }
    expect(result.zone).toBe("HOT");
    expect(result.ratioClamped).toBe(200);
    expect(result.angleDeg).toBeCloseTo(-30, 3);
  });
});
