# Progreso del Hito 10 (para retomar)

- [x] Rama `hito-10-dashboard` desde `origin/main` (79419fc, con hito-9); main sin tocar
- [x] Búsqueda del código exportado de v0: no existe; `docs/dashboard.md` es la única fuente
- [x] spec.md, plan.md y autorrevisión
- [x] Dominio `domain/stats.py` y pruebas
- [x] `services/dashboard.py` y pruebas con el almacén en memoria
- [x] API (`api/`): sesión, rutas, middlewares, solo lectura, registros; pruebas
- [x] `scripts/create_dashboard_role.sql`, `Dockerfile.dashboard`, servicio en Compose
- [x] Integración contra Postgres temporal (rol de solo lectura)
- [x] Frontend `web/`: tokens, copy, format, componentes, API, estados, tema
- [x] Pruebas del frontend: Vitest, tsc, eslint; Playwright + axe
- [x] CI (job `web`)
- [x] Docs: plan-tecnico, HITOS, README, `docs/dashboard.md` (solo columna "Campo de la API")
- [x] Suite completa (pytest, ruff, frontend)
- [x] verificacion.md y reporte
- [ ] Propietario: revisión, rol en el homelab, secreto, commits (verificacion.md, sección 3)
