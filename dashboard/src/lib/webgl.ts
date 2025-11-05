/**
 * WebGL Feature Detection
 *
 * Detects if WebGL is available in the browser.
 * Used to gracefully fallback to 2D maps when WebGL is not supported.
 */

export interface WebGLCheckResult {
  ok: boolean;
  reason?: string;
}

export function hasWebGL(): WebGLCheckResult {
  try {
    const canvas = document.createElement("canvas");
    const gl =
      canvas.getContext("webgl2") ||
      canvas.getContext("webgl") ||
      (canvas.getContext("experimental-webgl") as WebGLRenderingContext | null);

    if (!gl) {
      return { ok: false, reason: "no-context" };
    }

    // Optional: Sanity check for basic WebGL extensions
    const hasExtension = gl.getExtension && gl.getExtension("OES_standard_derivatives");

    return { ok: true, reason: hasExtension ? "ok" : "ok-no-ext" };
  } catch (e: any) {
    return { ok: false, reason: e?.message || "exception" };
  }
}
