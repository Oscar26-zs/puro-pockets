/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { fileURLToPath, URL } from "node:url"
import { defineConfig } from "vite"

// Dashboard de Puro Pockets (Hito 10). En desarrollo, /api va a la API local (python -m
// puro_pockets.api en 127.0.0.1:8080). La compilación no incluye datos de ejemplo ni mapas de
// código fuente.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
    // Una sola copia de React (en Windows, c:\ y C:\ pueden resolverse como dos módulos)
    dedupe: ["react", "react-dom"],
  },
  server: {
    host: "127.0.0.1",
    proxy: { "/api": { target: "http://127.0.0.1:8080", changeOrigin: false } },
  },
  preview: { host: "127.0.0.1" },
  // Recharts pesa: un solo paquete de ~700 kB (≈200 kB comprimido) es aceptable en red privada
  build: { sourcemap: false, outDir: "dist", emptyOutDir: true, chunkSizeWarningLimit: 800 },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
})
