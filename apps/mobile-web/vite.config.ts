import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, resolve(__dirname, "../../"), "");
  const apiPort = env.API_PORT ?? "8000";
  const mobileWebPort = parseInt(env.MOBILE_PORT ?? "8090", 10);

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": resolve(__dirname, "src"),
      },
    },
    server: {
      host: env.MOBILE_WEB_HOST ?? "127.0.0.1",
      port: mobileWebPort,
      proxy: {
        "/api": {
          target: `http://localhost:${apiPort}`,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ""),
        },
      },
    },
  };
});
