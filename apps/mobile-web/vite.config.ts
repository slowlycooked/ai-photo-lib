import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, resolve(__dirname, "../../"), "");
  const apiPort = env.API_PORT ?? "8000";
  const mobileWebPort = parseInt(env.MOBILE_PORT ?? "8090", 10);
  const allowedHosts = (env.VITE_ALLOWED_HOSTS ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": resolve(__dirname, "src"),
      },
    },
    server: {
      host: env.MOBILE_WEB_HOST ?? "0.0.0.0",
      port: mobileWebPort,
      allowedHosts: allowedHosts.length > 0 ? allowedHosts : undefined,
      proxy: {
        "/api": {
          target: `http://localhost:${apiPort}`,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ""),
        },
      },
    },
    preview: {
      host: env.MOBILE_WEB_HOST ?? "0.0.0.0",
      port: mobileWebPort,
      allowedHosts: allowedHosts.length > 0 ? allowedHosts : undefined,
    },
  };
});
