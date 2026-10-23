import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

/**
 * Dev server notes
 * ----------------
 * `allowedHosts: true` lets the app be opened through a forwarding host
 * (tunnel, cloud IDE, sandbox preview) as well as localhost. Vite's default
 * host check would answer 403 to any hostname it does not recognise.
 *
 * `/api` is proxied to the FastAPI service so the browser only ever talks to
 * one origin — no CORS preflight, and no hard-coded `localhost:8000` in the
 * bundle. Change the target here if the backend runs elsewhere.
 */
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: false,
    allowedHosts: true,
    proxy: {
      "/api": {
        target: process.env.VITE_PROXY_TARGET || "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: path => path.replace(/^\/api/, ""),
      },
    },
  },
  preview: {
    host: "0.0.0.0",
    allowedHosts: true,
    proxy: {
      "/api": {
        target: process.env.VITE_PROXY_TARGET || "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: path => path.replace(/^\/api/, ""),
      },
    },
  },
});
