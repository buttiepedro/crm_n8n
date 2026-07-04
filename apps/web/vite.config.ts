import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// En dev local (npm run dev) el proxy apunta al backend en localhost;
// en Docker, nginx hace el proxy hacia el servicio `api` de la red interna.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 8000,
    proxy: {
      "/api": {
        target: process.env.VITE_API_URL ?? "http://localhost:8080",
        changeOrigin: true,
      },
    },
  },
});
