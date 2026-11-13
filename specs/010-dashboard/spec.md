# Feature Specification: Dashboard y estadísticas

**Feature Branch**: `hito-10-dashboard`

**Created**: 2026-11-12

**Status**: Implementado (pendiente de la verificación del propietario en el homelab)

**Input**: User description (prompt del Hito 10 en `HITOS.md`): "El propietario quiere consultar en
una página web privada cuánto ingresó, cuánto gastó y cuánto le queda por bolsa, en qué categorías
gasta más, cómo evolucionan sus meses y cómo van sus metas de ahorro. Los datos deben coincidir
exactamente con los que le reporta Claude. Incluye pruebas automáticas que verifiquen los criterios
de aceptación."

**Hito**: 10 (Dashboard y estadísticas), según `HITOS.md`. Flujo sin Spec Kit (sección 1 de
`HITOS.md`).

## Resumen de decisiones

**[DECIDIDO] por el propietario (2026-11-12, prompt del Hito 10, sin clarify):**

- API en **FastAPI**, solo `GET` salvo el inicio y el cierre de sesión (`POST`); el resto, 405.
- **Capa de lectura** que reutiliza `services/` (Hitos 5 a 9) sin duplicar reglas (constitución
  9.1, 11.1, 11.2). Ningún servicio de lectura escribe.
- **Servicio `dashboard`** en Compose: API en `/api` y frontend compilado, imagen de varias etapas,
  publicado en `127.0.0.1` por defecto (variable para una IP privada), healthcheck y
  `restart: unless-stopped`. No pasa por el MCP.
- **Cambio del 2026-11-12 (tras la verificación en el homelab):** el propietario decide publicarlo
  también por el túnel de Cloudflare en `dash.puropockets.space`, siempre detrás de Cloudflare
  Access, que el dashboard verifica (403 sin token válido). Reemplaza "no se enruta por el túnel".
- **Autenticación propia:** verificación argon2 y `scripts/hash_password.py` del Hito 3 con
  `OWNER_PASSWORD_HASH`; cookie firmada (`DASHBOARD_SESSION_SECRET` ≥ 32 bytes), HttpOnly,
  SameSite=Strict, Secure configurable, 12 h; límite de intentos por IP; sin sesión, `/api` → 401.
  Sin tablas nuevas.
- **Rol de solo lectura** (`DASHBOARD_DATABASE_URL`) sin acceso a `oauth_*`; la API se niega a
  arrancar si el rol puede escribir o leer `oauth_*`; sin respaldo al rol propietario.
- **Cabeceras de seguridad**, sin CORS; **privacidad** (sin CDN, analíticas, otros orígenes ni datos
  financieros en almacenamiento del navegador o URL, salvo el mes; solo el tema se guarda).
- **Los valores salen del servidor:** el frontend no recalcula saldos, porcentajes ni estimaciones.
- **Frontend:** React + Vite + TypeScript + Tailwind + shadcn/ui + Recharts, en `web/`.
- **Fuente visual:** `docs/dashboard.md` (manda en lo visual; la constitución y el plan técnico
  mandan en datos y reglas).

**[PROPUESTO] en este hito (se listan en el reporte):**

- P1 **Fecha estimada de una meta** calculada por la API: `⌈faltante ÷ promedio mensual⌉` meses
  desde el mes actual, solo con `projectable = true` y faltante > 0 (RN-28 lo deja a Claude en el
  MCP; el MCP no cambia).
- P2 **"Ahorrado" del mes** (plan técnico, sección 13.3): asignado a acumulables por los ingresos
  del mes (sin saldo inicial) + transferencias recibidas por acumulables − enviadas + sobrantes de
  cierre enviados a acumulables, con desglose por origen.
- P3 **"Disponible" del mes** (tarjeta): Σ disponible (11.1) de las bolsas de consumo activas del
  mes, tal como lo entrega `get_summary`.
- P4 **Alertas** calculadas por la API: uso alto ≥ 80 % del ajustado, sobregasto ≥ 100 % o
  disponible negativo (RN-38, plan técnico 13.2), cierre pendiente (RN-49), extras sin asignar
  (RN-06).
- P5 **Compilación del frontend:** dentro de la imagen; si no cabe en los 4 GB del homelab, se
  compila la imagen en la PC y se copia (README).
- P6 **Playwright y axe** corren en el equipo de desarrollo; el CI corre lint, typecheck y las pruebas
  de componentes y de la API.
- P7 **Panel de desarrollo** y `?state=` solo en la compilación de desarrollo (no en producción).
- P8 **Sesión sin estado en la base:** el cierre de sesión borra la cookie y revoca su identificador
  en memoria; un reinicio olvida las revocaciones (la cookie sigue venciendo a las 12 h). Rotar
  `DASHBOARD_SESSION_SECRET` invalida todas.
- P10 **Detección de "llegó por Cloudflare"** por el nombre público o por las cabeceras `CF-Ray`, `CF-Connecting-IP` o `Cf-Access-Jwt-Assertion`; sesión de Access configurada en Cloudflare (24 h sugeridas) independiente de las 12 h de la cookie del dashboard.
- P9 **Paginación** de movimientos: 10 por página, como máximo 10 páginas (tope de 100 de
  `list_transactions`).

## Fuente de diseño y diferencias

`docs/dashboard.md` describe un código exportado de v0 (`app/globals.css`, `app/layout.tsx`,
`components/puro-dashboard.tsx`, `data/mock.ts`, `lib/copy.ts`, `lib/format.ts`). **Ese código y las
capturas no existen en el repositorio** (búsqueda en `docs/` y en la carpeta del proyecto,
2026-11-12). Por eso la comparación token por token y texto por texto no se pudo hacer contra el
código: se toma `docs/dashboard.md` como única fuente (manda sobre el código, según el encargo), que
trae literalmente los tokens (§3), `copy.ts` (§10), `format.ts` (§9), los puntos de corte (§4) y los
componentes (§7).

Diferencias deliberadas respecto a lo que describe `docs/dashboard.md` (lo visual se conserva; cambia
el comportamiento que el documento marca como prototipo o pendiente):

| # | `docs/dashboard.md` | Implementación | Motivo |
|---|---|---|---|
| D1 | Datos de `data/mock.ts` | Datos de la API; el mock solo como fixture de pruebas | Encargo |
| D2 | «Entrar» sin manejador; texto `noLogin` | Inicio de sesión real; `noLogin` no se muestra | Autenticación del hito |
| D3 | Avisos estáticos escritos en el componente | Avisos de la API con las mismas plantillas de texto | P4 |
| D4 | «₡310.000 en total» fijo | Total de `top_categories` | Datos reales |
| D5 | Meta: fecha calculada en el componente | `estimated_month` de la API | P1 |
| D6 | `aria-valuenow` puede superar `aria-valuemax` (§13) | `aria-valuenow` con tope 100 y `aria-valuetext` con el valor real | Pendiente de §16 |
| D7 | Panel móvil de filtros sin rol de diálogo ni foco | `role="dialog"`, `aria-modal`, `aria-expanded`, Escape y foco inicial | Pendiente de §16 |
| D8 | Panel de desarrollo siempre visible | Solo en desarrollo | P7 |
| D9 | Movimientos sin orden ni paginación | Más recientes primero, 10 por página con tope | P9 |
| D10 | Familia tipográfica «No diseñado» | Pila del sistema de Tailwind (sin archivos de fuente que alojar) | Privacidad |
| D11 | Textos visibles que no están en `copy.ts` («Todo está al día.», plantillas de avisos, etiquetas de ingresos y motivos) | En `web/src/lib/labels.ts`; `copy.ts` queda literal | Fidelidad de `copy.ts` |

## User Scenarios & Testing

### Historia 1: ver el resumen del mes (P1)

El propietario abre el dashboard, inicia sesión y ve el mes actual: ingresos, gastado, disponible y
ahorrado, los extras sin asignar, avisos, la evolución de 6 meses, los gastos fijos y el gasto por
categoría.

**Prueba independiente:** con datos sintéticos, los totales del resumen son idénticos a `get_summary`.

1. **Dado** un mes con salario, gastos y un gasto anulado, **cuando** pide el resumen, **entonces**
   ingresos, gastado y bolsas coinciden con `get_summary` y el anulado no suma.
2. **Dado** un mes cerrado, **cuando** lo consulta, **entonces** ve «Mes cerrado» y el aviso de solo
   lectura (RN-48, RN-50).
3. **Dado** un mes terminado sin cerrar, **entonces** ve «Falta cerrar <mes>» (RN-49).
4. **Dado** un extra pendiente, **entonces** aparece en «Sin asignar» y en los avisos (RN-06).

### Historia 2: bolsas y metas (P1)

Ve cada bolsa con presupuesto original y ajustado, recibidas, enviadas, gastado, disponible y % usado
(consumo, 9.1 y 11.1) o saldo (acumulable, 11.2), y su meta con avance, faltante y fecha estimada.

1. Las cifras de cada bolsa son idénticas a `get_bolsa_status` y las de cada meta a
   `get_goal_progress` (11.3, RN-23).
2. Una bolsa con ≥ 80 % muestra «Uso alto»; con ≥ 100 % o negativa, «Sobregasto» en rojo (RN-38).
3. Con `projectable = false`, «Sin estimación» (RN-28).

### Historia 3: movimientos con filtros (P2)

Filtra por tipo, bolsa y mes, e incluye o no los anulados; los anulados se ven marcados y no suman.

1. Los movimientos son idénticos a `list_transactions` con los mismos filtros.
2. Por defecto no incluye anulados; con el filtro aparecen con «Anulado» (RN-53).

### Historia 4: acceso privado (P1)

Solo el propietario entra, solo desde la red privada.

1. Sin sesión, todo `/api` responde 401; contraseña mala → 401 y, tras 5 fallos, 429.
2. La cookie es HttpOnly y SameSite=Strict, con Secure según la variable, y vence a las 12 h.
3. `mcp.puropockets.space` no sirve `/` ni `/api`; el puerto se publica en `127.0.0.1`.
4. Por `dash.puropockets.space`, sin un token válido de Cloudflare Access todo responde 403, incluido
   el inicio de sesión; con token, sigue pidiendo la contraseña.

### Casos límite

- Mes sin movimientos: tarjetas en cero y «No hay movimientos para mostrar.».
- Mes futuro: el selector lo deshabilita; la API lo acepta y devuelve ceros.
- USD: se muestra el monto original sin convertir («Sin convertir»); los totales van en colones.
- Bolsa archivada: no aparece en el resumen de bolsas (igual que `get_summary`).
- Meta lograda o con faltante 0: sin fecha estimada.
- Error de red o 500: tarjeta de error con «Reintentar»; 401: pantalla de inicio de sesión.

## Requirements

### Funcionales

- **FR-001** API de solo lectura sobre `LedgerService` (constitución, Gobernanza, regla no
  negociable 2; plan técnico "Movimientos" a "Cierre de mes"). Resumen, bolsas y metas, movimientos,
  categorías y gastos fijos salen de `get_summary`, `get_bolsa_status`, `get_goal_progress`,
  `list_transactions`, `top_categories` y `list_pending_recurring` sin recalcular.
- **FR-002** Cálculos nuevos (P1, P2, P3, P4, evolución) como funciones puras en `domain/stats.py`
  sobre las mismas entradas de `pocket_figures`; los anulados no suman (11, RN-53).
- **FR-003** Endpoints: sesión (`GET`, `POST login`, `POST logout`), resumen, bolsas, movimientos
  (tipo, bolsa, mes, anulados, página), categorías, evolución de 6 meses, gastos fijos, cierres
  pendientes. Solo los campos que la pantalla usa (principio 3.10, minimización).
- **FR-004** Meses cerrados marcados (RN-48, RN-50), cierres pendientes (RN-49), extras sin asignar
  (RN-06), presupuesto original y ajustado (9.1).
- **FR-005** Autenticación según "Resumen de decisiones"; sin tablas nuevas.
- **FR-006** Rol de solo lectura con comprobación al arrancar; sin respaldo al rol propietario.
- **FR-007** Cabeceras: `Content-Security-Policy` (`default-src 'self'`, `frame-ancestors 'none'`),
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` en
  `/api`. Sin CORS.
- **FR-008** Registros del servidor y mensajes de error sin montos, notas, descripciones ni nombres
  de metas (plan técnico, "Registros" de cada hito); sin registro de acceso con la consulta.
- **FR-009** Frontend con tokens, tipografía, puntos de corte, componentes, `copy.ts` y `format.ts`
  de `docs/dashboard.md`; estados de carga, vacío, error y mes cerrado; tema claro, oscuro y sistema
  (solo el tema en `localStorage`).
- **FR-010** Servicio `dashboard` en Compose con perfil `dashboard`, healthcheck, reinicio y puerto
  en `${DASHBOARD_BIND_IP:-127.0.0.1}`; no enrutado por el túnel.
- **FR-011** Pruebas automáticas positivas y negativas (constitución, regla no negociable 4) de la
  API, del frontend (componentes, typecheck, lint) y de responsive y accesibilidad (Playwright y
  axe).

### Entidades

Sin entidades nuevas en la base. Respuestas de la API en `plan.md` ("Contrato de la API").

## Success Criteria

- **SC-001** Para los mismos datos sintéticos, resumen, bolsas, metas y movimientos de la API son
  **idénticos** a `get_summary`, `get_bolsa_status`, `get_goal_progress` y `list_transactions`
  (prueba que llama a las tools por MCP).
- **SC-002** 100 % de las rutas de `/api` responden 401 sin sesión, y 405 con otro verbo.
- **SC-003** La API no arranca con un rol que puede escribir en una tabla de negocio o leer una
  `oauth_*` (prueba contra Postgres).
- **SC-004** "Ahorrado" y evolución coinciden con los valores esperados de un conjunto sintético
  calculado a mano, con anulados, transferencias y un cierre.
- **SC-005** Ninguna línea de registro de las pruebas contiene montos, descripciones ni nombres de
  metas sintéticos.
- **SC-006** Sin scroll horizontal en 320, 360, 768, 1024, 1280 y 1920 px; navegación con objetivos
  de al menos 44 px; cero violaciones graves (serious o critical) de axe en claro y oscuro.
- **SC-007** `ruff`, `pytest`, `eslint`, `tsc` y `vitest` sin errores.

## Supuestos

- El propietario accede por Tailscale o túnel SSH; el homelab no abre puertos a internet.
- Una sola persona usa el dashboard; el límite de intentos vive en memoria.
- El dashboard muestra lo mismo que Claude; no se agregan reglas de negocio nuevas.
