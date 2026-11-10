import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8096",
      "/v1": "http://127.0.0.1:8096",
      "/auth": "http://127.0.0.1:8096",
      "/health": "http://127.0.0.1:8096",
      "/mcp": "http://127.0.0.1:8096",
      "/.well-known": "http://127.0.0.1:8096",
    },
  },
});
