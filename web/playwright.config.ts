import { defineConfig, devices } from "@playwright/test"

// Responsive y accesibilidad (Hito 10). Corre en el equipo de desarrollo contra la compilación de
// producción (`vite preview`), con la API simulada por page.route: no necesita base de datos ni
// datos reales. El CI de GitHub no la ejecuta (decisión P6).
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  reporter: [["list"]],
  use: { baseURL: "http://127.0.0.1:4173", ...devices["Desktop Chrome"] },
  webServer: {
    command: "npm run build && npm run preview",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: false,
    timeout: 180_000,
  },
})
