import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react()],
    server: {
      port: Number(env.VITE_DEV_SERVER_PORT ?? 5173),
      proxy: {
        '/api': {
          target: env.VITE_API_BASE_URL || 'http://localhost:8082',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
      },
    },
    preview: {
      port: 4173,
    },
    build: {
      sourcemap: mode !== "production",
      outDir: "dist",
    },
    optimizeDeps: {
      include: ['mapbox-gl'],
    }
  };
});
