# Plan técnico de Puro Pockets

**Versión:** 0.11
**Fecha:** 2026-11-11
**Capa:** 2 en la gobernanza de `.specify/memory/constitution.md`. Decide la técnica; si contradice a
la constitución, gana la constitución y se corrige este documento.

Este documento contiene el stack, la arquitectura, el catálogo de tools y el esquema de datos. Las
reglas de negocio no se repiten aquí: se citan por su identificador (`RN-xx`). La numeración de las
secciones 12, 13, 15, 16 y 17 conserva la del documento de origen v0.3
(`docs/origen/CONSTITUCION-origen.md`, archivado). Se actualiza al cerrar cada hito si cambió el
esquema o la arquitectura.

**Hoja de ruta:** el alcance, el orden y los criterios de cierre de cada hito están en
[`HITOS.md`](../HITOS.md). Este documento no copia el mapa de hitos.

---

## Stack

| Área | Elección | Estado |
|---|---|---|
| Lenguaje | Python (3.12 o superior); el proyecto fija 3.14 en `.python-version` y en la imagen `python:3.14-slim` | [DECIDIDO] (decisión 10, Hito 1) |
| Gestor de entornos y dependencias | uv 0.12.5 (fijado en el `Dockerfile` y en el CI), con dependencias fijadas en `uv.lock` | [DECIDIDO] (Hito 1) |
| Base de datos | PostgreSQL **18** en Docker (Docker Compose), imagen `postgres:18-alpine` (nunca `latest`), con volumen persistente y puerto atado a `127.0.0.1` | [DECIDIDO] (Hito 1) |
| Acceso a datos | SQLAlchemy 2.x con el driver psycopg 3, en modo síncrono (las comprobaciones bloqueantes corren en un hilo; ver `specs/001-cimientos/research.md`, R3) | [DECIDIDO] (Hito 1) |
| Migraciones | Alembic | [DECIDIDO] |
| Servidor MCP | Transporte Streamable HTTP desde el Hito 1, publicado solo en `127.0.0.1`; remoto por HTTPS desde el Hito 2 | [DECIDIDO] (decisión 9, Hito 1) |
| SDK de MCP | `mcp==2.3.0` (versión exacta); servidor con `MCPServer` importada desde `mcp.server.mcpserver`. Verificado el 2026-11-09 en PyPI y en la guía oficial de migración v1 → v2, y confirmado al implementar el Hito 1 (prueba de humo `tests/unit/test_sdk_import.py`). Protección contra DNS rebinding configurada de forma explícita para hosts locales. | [DECIDIDO] (Hito 1) |
| Verificación automática (CI) | En cada push a GitHub: ruff y pruebas unitarias. Las pruebas de integración corren en local. | [DECIDIDO] (Hito 1) |
| Publicación | Túnel con nombre de Cloudflare (remotamente administrado), contenedor `cloudflare/cloudflared:2026.10.3`, hacia `https://mcp.puropockets.space` (ver "Acceso remoto") | [DECIDIDO] (decisión 9, Hito 2) |
| Autenticación del MCP | OAuth 2.1: el MCP es servidor de recursos y también servidor de autorización (ver "Autenticación OAuth") | [DECIDIDO] (Hito 3) |
| Servidor de autorización de OAuth | Propio y mínimo, para un único usuario, sobre el módulo de autenticación del SDK `mcp==2.3.0`; contraseña con argon2 (`argon2-cffi`) | [DECIDIDO] (Hito 3) |
| Pruebas y estilo | pytest y ruff; CI en GitHub Actions | [DECIDIDO] (Hito 1) |
| Dashboard | React + Vite + TypeScript + Tailwind, con una librería de gráficos | [PROPUESTO] (sección 16) |
| API del dashboard | Framework por decidir | [ABIERTO]: se resuelve en el Hito 10 |
| Ejecución | Homelab del propietario | [DECIDIDO] |

### Convención de idioma [DECIDIDO] (Hito 1)

- **En inglés:** nombres de código (módulos, clases, funciones, variables), tablas, columnas y tools
  MCP.
- **En español:** documentación y mensajes que ve el usuario (incluidos los mensajes de error que
  devuelven las tools).
- El esquema de referencia de la sección 17 y la tabla concepto → tabla ya usan los nombres en
  inglés de todas las tablas (las últimas, `month_closures` y `closure_adjustments`, en el Hito 9).
- **"Bolsa" en el código [DECIDIDO] (Hito 4):** `pocket` en tablas, columnas y código (`pockets`,
  `pocket_id`). Las tools conservan los nombres del catálogo de la sección 12.1 (`list_bolsas`,
  `create_bolsa`, `get_bolsa_status`…), porque "bolsa" es el término del glosario.

### Actualizar el SDK de MCP

Actualizar el SDK es una decisión deliberada, nunca automática:

1. Cambiar el número de versión de `mcp` en `pyproject.toml` y regenerar `uv.lock`.
2. Correr todas las pruebas (unitarias, de integración y la prueba de humo que importa `MCPServer`
   desde `mcp.server.mcpserver`).
3. Anotar en este documento la nueva versión, la fecha de verificación y la ruta de importación.

### Medición de memoria

- **Cuándo:** con los servicios `db` y `mcp` recién levantados y estabilizados (en reposo), y otra
  vez después de 20 llamadas a `ping`.
- **Cómo:** `docker stats --no-stream`, tomando la columna de uso de memoria de cada servicio.
- **Dónde:** en la tabla siguiente, con fecha y equipo. La medición en el homelab se agrega en el
  Hito 2.

| Fecha | Equipo | Servicio | En reposo | Tras 20 `ping` |
|---|---|---|---|---|
| 2026-11-09 | Equipo de desarrollo (Windows 11, Docker Desktop con WSL 2, 7,7 GiB para Docker) | `db` | 25,1 MiB | 27,8 MiB |
| 2026-11-09 | Equipo de desarrollo (Windows 11, Docker Desktop con WSL 2, 7,7 GiB para Docker) | `mcp` | 75,7 MiB | 78,6 MiB |

### Estructura del código (Hito 1)

```text
src/puro_pockets/
├── __main__.py    # arranque: configuración, motor, servicios y servidor MCP
├── config.py      # variables de entorno; error en español si falta alguna
├── domain/        # reglas puras: no importa MCP ni base de datos (prueba de arquitectura)
├── services/      # casos de uso (p. ej. comprobación de salud con tiempo límite)
├── db/            # motor de SQLAlchemy y acceso a la base
└── mcp/           # MCPServer y tools delgadas que llaman a services
migrations/        # Alembic (0001_base sin tablas)
tests/unit/        # corren en el CI
tests/integration/ # requieren docker compose up; corren en el equipo de desarrollo
scripts/ping.py    # cliente de prueba por Streamable HTTP
```

Servicios de Docker Compose: `db` (`postgres:18-alpine`, volumen `pgdata` en `/var/lib/postgresql`,
puerto `127.0.0.1:5432`, healthcheck con `pg_isready`) y `mcp` (imagen propia, puerto
`127.0.0.1:8000`, arranca cuando `db` está healthy). Desde el equipo, la URL de la base usa
`127.0.0.1` y no `localhost` (en Windows, `localhost` intenta IPv6 primero y cada conexión tardaba
5 segundos).

### Acceso remoto [DECIDIDO] (Hito 2)

- **Dominio:** `puropockets.space`, registrado en Namecheap, con el DNS gestionado por Cloudflare.
- **Subdominio del MCP:** `mcp.puropockets.space`. URL del conector de claude.ai:
  `https://mcp.puropockets.space/mcp` (sin autenticación hasta el Hito 3).
- **Recorrido:** Claude → Cloudflare → túnel (servicio `cloudflared` de Compose, en el homelab) →
  `http://mcp:8000` por la red interna de Docker → servidor MCP. El homelab no abre puertos hacia
  internet; `mcp` y `db` solo publican puertos en `127.0.0.1`.
- **Túnel:** remotamente administrado (nombre público configurado en el panel de Cloudflare:
  `mcp.puropockets.space` → `HTTP mcp:8000`, sin cambiar el *HTTP Host Header*). Imagen
  `cloudflare/cloudflared:2026.10.3`, comando `tunnel --no-autoupdate --metrics 0.0.0.0:20241 run`.
  El token se lee de `CF_TUNNEL_TOKEN` en el `.env` del homelab y llega al contenedor como
  `TUNNEL_TOKEN`; nunca se guarda en el repositorio.
- **Activación:** el servicio `cloudflared` tiene el perfil `tunnel`; solo arranca donde
  `COMPOSE_PROFILES=tunnel` (el homelab). En el equipo de desarrollo no arranca.
- **Hosts y orígenes permitidos** (protección contra DNS rebinding del SDK; `Host` inválido → 421,
  `Origin` inválido → 403, sin `Origin` → permitido):
  - Hosts: `127.0.0.1:*`, `localhost:*`, `[::1]:*` y el valor de `MCP_PUBLIC_HOSTNAME`
    (`mcp.puropockets.space` y `mcp.puropockets.space:*`).
  - Orígenes: los locales (`http://127.0.0.1:*`, etc.), `https://mcp.puropockets.space` y los de
    `MCP_ALLOWED_ORIGINS` (documentado: `https://claude.ai,https://claude.com`).
- **Reinicio:** `restart: unless-stopped` en `db`, `mcp` y `cloudflared`; Docker habilitado al
  arranque del sistema en el homelab.
- **Salud:** `db` con `pg_isready`; `mcp` con `python scripts/ping.py` dentro del contenedor;
  `cloudflared` con `cloudflared tunnel --metrics 127.0.0.1:20241 ready` (consulta `/ready`). El túnel
  arranca cuando `mcp` está healthy.
- **Operación:** pasos manuales, actualización del despliegue y comprobación de salud en el README
  ("Despliegue en el homelab").


### Autenticación OAuth [DECIDIDO] (Hito 3)

- **Servidor de autorización:** propio y mínimo, para un único usuario (el propietario), dentro del
  mismo servidor MCP. El SDK aporta los endpoints, PKCE S256 y la validación Bearer; el proyecto aporta
  el proveedor (`services/oauth.py`), el almacén SQL (`db/oauth_store.py`) y la página de inicio de
  sesión (`mcp/login.py`).
- **Endpoints** (emisor `https://mcp.puropockets.space`): `/authorize`, `/token`, `/revoke`,
  `/register` (solo con el registro abierto), `/login`, `/.well-known/oauth-authorization-server`
  (RFC 8414) y `/.well-known/oauth-protected-resource/mcp` (RFC 9728, recurso
  `https://mcp.puropockets.space/mcp`). Sin token, `/mcp` responde 401 con
  `WWW-Authenticate: Bearer ..., resource_metadata="…"`.
- **Clientes:** registro dinámico (RFC 7591) cerrado por defecto (`OAUTH_REGISTRATION_ENABLED`); solo
  clientes públicos (sin secreto), solo URL de retorno de `OAUTH_ALLOWED_REDIRECT_URIS`
  (`https://claude.ai/api/mcp/auth_callback`, `https://claude.com/api/mcp/auth_callback`), máximo
  `OAUTH_MAX_CLIENTS` (10) y 5 registros por hora. Alternativa: cliente propio con
  `scripts/register_client.py`. Claude Code (redirecciones locales) queda fuera.
- **Duraciones** (configurables): acceso 1 hora, refresco 30 días con rotación, código 5 minutos de un
  solo uso. Reutilizar un refresco ya rotado revoca toda su cadena. `OAUTH_SHORT_LIFETIMES=true`:
  acceso 2 minutos y refresco 15 minutos, solo para pruebas.
- **Scopes:** `mcp` (requerido) y `offline_access` (anunciado, para que Claude pida refresco). Los
  tokens se ligan al recurso y se rechazan los de otro recurso (`validate_token_resource=True`).
- **Almacenamiento** (migración `0002_oauth`): `oauth_clients`, `oauth_authorization_codes`,
  `oauth_access_tokens`, `oauth_refresh_tokens`. Solo hashes SHA-256 de códigos y tokens (tokens
  opacos de 256 bits con prefijo `ppc_`, `ppa_`, `ppr_`).
- **Contraseña:** hash argon2id en `OWNER_PASSWORD_HASH` (entre comillas simples en `.env`), generado
  con `scripts/hash_password.py`; los parámetros viajan dentro del hash y se ajustan para que la
  verificación tarde menos de 1 segundo en el homelab (`--benchmark`). Sin hash válido, el inicio de
  sesión queda deshabilitado.
- **Límite de intentos (solo inicio de sesión):** 5 fallos por IP (`CF-Connecting-IP`) en 15 minutos
  bloquean esa IP; 20 fallos globales en 15 minutos bloquean el inicio de sesión 5 minutos. Nunca
  afecta a `/mcp` con token válido.
- **Revocación:** endpoint `/revoke` (RFC 7009) y `scripts/revoke_tokens.py --yes` (todo).
- **Registros:** sin contraseñas, hashes, códigos ni tokens; se registran el dominio de retorno, los
  registros de clientes, los inicios de sesión, los refrescos, las reutilizaciones y las revocaciones.
- **Observaciones del SDK:** el endpoint `/revoke` exige `client_secret` aunque sea vacío para clientes
  públicos (defecto de `RevocationRequest`); se deja documentado y cubierto por una prueba que avisará
  cuando se corrija. La comparación de PKCE y los metadatos `client_secret_*` se dejan como están.

### Presupuesto [DECIDIDO] (Hito 4)

- **Código:** `domain/months.py` (mes `YYYY-MM`), `domain/pockets.py` (comportamientos, nombres sin
  distinguir mayúsculas), `domain/allocation.py` (RN-01, RN-03, RN-08), `domain/initial_balance.py`
  (RN-54), `domain/balances.py` (11.1, 11.2 y comprobación del invariante 11.4),
  `services/budget.py`, `db/budget_store.py` y `mcp/budget_tools.py`. Migración `0003_budget`.
- **Mes actual:** `APP_TIMEZONE` (por defecto `America/Costa_Rica`, con `zoneinfo`; `tzdata` es
  dependencia directa para Windows).
- **Herencia de porcentajes (RN-03):** se resuelve al consultar, sin guardar nada. Solo se editan el
  mes actual y los futuros, así que lo que un mes pasado heredó no cambia.
- **Saldo inicial:** `load_initial_balance` exige `confirm=true`; índice único parcial
  `ux_incomes_single_initial_balance` (el Hito 5 lo recrea excluyendo los anulados). No existe tool
  ni script que lo borre.
- **Errores:** las reglas lanzan `DomainError` y las tools lo devuelven como `ToolError` (is_error,
  mensaje en español). El SDK registra ese mensaje, así que los mensajes nunca incluyen montos. Las
  bibliotecas que en DEBUG registran cuerpos de respuesta (`sse_starlette`,
  `mcp.server.streamable_http`) quedan fijadas en INFO.
- **Downgrade protegido:** `0003_budget` aborta el downgrade si hay datos, salvo con
  `ALLOW_DESTRUCTIVE_DOWNGRADE=true`.
- **Pruebas de integración:** base temporal `pp_test_<aleatorio>` creada y borrada por las pruebas;
  se niegan a correr contra cualquier otra base. El invariante se prueba con 200 conjuntos sintéticos
  en memoria y 40 en Postgres (`tests/synthetic.py`, semilla fija).

### Movimientos [DECIDIDO] (Hito 5)

- **Código:** `domain/money.py` (monedas y conversión, RN-55 a RN-57), `domain/ledger.py`
  (referencias, fechas, mes del salario), `domain/categories.py`, `domain/idempotency.py`,
  `domain/balances.py` (11.1 y 11.2 con gastos; invariante 11.4 con gastos y anulaciones),
  `services/ledger.py`, `db/ledger_store.py`, `mcp/ledger_tools.py` y `mcp/inputs.py` (entradas sin
  `float`). Migración `0004_movements`.
- **Montos sin `float`:** colones enteros; USD en centavos; tipo de cambio en colones por dólar ×100.
  Las tools aceptan colones como entero y USD o tipo de cambio como entero o texto con hasta 2
  decimales (`"10.50"`), leído con `Decimal`; un número JSON con decimales se rechaza (llegaría como
  `float`). Conversión: `monto_crc = (centavos × tipo_cambio_x100 + 5 000) // 10 000` (half-up), una
  sola vez al registrar. Se rechazan el tipo de cambio faltante (nunca se asume), fuera de
  `USD_RATE_MIN`..`USD_RATE_MAX` (por defecto 300 y 1000) y las conversiones que dan 0 colones.
- **Salario:** mes presupuestario = mes siguiente a la fecha (constitución 5.1) u otro explícito;
  porcentajes del mes o heredados (RN-03); reparto RN-08 entre las bolsas con porcentaje mayor que
  0; el porcentaje usado se guarda en cada reparto. `preview_income` y `add_income` sin `confirm` no
  guardan nada.
- **Gastos:** mes calendario de su fecha; cualquier bolsa activa; sin categoría = "pendiente de
  clasificar"; sin bolsa, la bolsa por defecto de la categoría. Un sobregasto se guarda y la
  respuesta lista las bolsas con saldo disponible.
- **Anulación:** `void_transaction` (vista previa sin `confirm`) marca `voided`, `voided_at` y
  `void_reason`; todo cálculo ignora lo anulado. Anular un ingreso revierte su reparto (RN-59).
  Anular el saldo inicial permite otra carga (índice único parcial con `AND NOT voided`). Solo se
  anula en un mes abierto (regla única de mes cerrado, Hito 9).
- **Referencias:** `I-<n>` (ingresos, incluido el saldo inicial) y `G-<n>` (gastos), con el número de
  fila; no se expone otro identificador.
- **Idempotencia:** `operation_id` obligatorio en `add_income` (al confirmar), `add_expense` y
  `void_transaction`. Tabla `idempotency_keys` con la huella SHA-256 del contenido normalizado y la
  respuesta original; el movimiento y su clave se guardan en una transacción, y la PK resuelve dos
  llamadas simultáneas.
- **Libro mayor inmutable en la base:** disparadores impiden borrar filas de `incomes`,
  `income_allocations` y `expenses`, modificar `income_allocations` y editar un movimiento salvo para
  anularlo (y `allocation_status`, que usará el Hito 6). Una anulación no se deshace.
- **Downgrade protegido:** `0004_movements` aborta si hay gastos, claves de operación o ingresos en
  USD o anulados, salvo con `ALLOW_DESTRUCTIVE_DOWNGRADE=true`.
- **Registros:** sin montos ni descripciones (solo referencia, mes, moneda y si hubo sobregasto).

### Extras y gastos fijos [DECIDIDO] (Hito 6)

- **Código:** `domain/extras.py` (porcentajes del extra y ficha de vista previa), `domain/recurring.py`
  (plantillas, vencimiento, pendientes), `services/extras.py` y `services/recurring.py` (mixins de
  `LedgerService`), `services/ledger_core.py` (base común: almacén, reloj, idempotencia),
  `services/records.py` (registros y protocolo `LedgerStore`), `mcp/extras_tools.py`. Migración
  `0005_extras_recurring`.
- **Ingreso extra:** `register_extra_income` guarda `kind = 'extra'` con `allocation_status =
  'pendiente'` y sin repartos; su mes presupuestario es el de su fecha (RN-09). Moneda y tipo de
  cambio como en el Hito 5. Mientras está pendiente no suma a ninguna bolsa ni al invariante y
  aparece como "sin asignar" (RN-06) en `get_summary` y `list_transactions` (cantidad, total en
  colones, y los de USD aparte con su total original).
- **Contexto:** `get_allocation_context(extra)` entrega solo agregados del mes del extra: bolsas
  activas (comportamiento, porcentaje vigente, presupuesto, gastado, disponible o saldo), gastos
  fijos pendientes (cantidad, atrasados, total CRC; los de USD aparte y sin convertir) y los
  porcentajes de los últimos 3 extras repartidos. Sin descripciones ni identificadores internos.
  Las metas se agregan en el Hito 7.
- **Reparto:** `confirm_allocation` valida enteros de 0 a 100 que suman 100 (RN-01) entre bolsas
  activas (las omitidas reciben 0; 100 % a una sola bolsa, también personalizada, RN-07); reparte
  con RN-08 (la última bolsa que recibe absorbe el residuo), guarda el porcentaje usado y pasa el
  extra a `repartido` en una transacción (`UPDATE … WHERE allocation_status = 'pendiente'`, así dos
  confirmaciones simultáneas no reparten dos veces). Un extra repartido no se reparte otra vez:
  corregir es anular y registrar de nuevo (RN-53, RN-59).
- **Claude recomienda, la app no (RN-05, principio 3.1).** Las instrucciones del servidor
  (`MCPServer(instructions=…)`, que el SDK `mcp==2.3.0` entrega en `InitializeResult.instructions`)
  y las descripciones de las tools explican el flujo: registrar → pedir contexto → proponer con una
  explicación breve → vista previa → esperar la aprobación explícita → confirmar.
- **Límite conocido de `confirm=true`:** por sí solo **no garantiza** que el modelo haya preguntado
  al propietario; un modelo podría enviarlo sin esperar la respuesta. Mitigación en capas:
  (1) `confirm=true` exige el `preview_token` que solo devuelve la vista previa con exactamente esos
  porcentajes (huella SHA-256 del extra, su monto y el reparto), así no se confirma un reparto que
  nunca se calculó ni se mostró; (2) instrucciones del servidor y descripciones que piden la
  aprobación explícita y aclaran que una respuesta ambigua no lo es; (3) el cliente (claude.ai)
  puede pedir permiso por cada llamada a una tool que escribe; (4) un error se corrige anulando
  (`void_transaction` revierte el reparto) y registrando de nuevo. La ficha no prueba la
  aprobación humana; eso queda en el cliente y en el propietario.
- **Gastos fijos:** `manage_recurring` (`crear`, `listar`, `actualizar`, `desactivar`) sobre
  `recurring_expenses`; nunca se borran (disparador). Nombre único entre las activas sin distinguir
  mayúsculas. El monto tiene historial en `recurring_expense_amounts`: cambiarlo vale desde el mes
  siguiente (o el de inicio, si es posterior) y los meses anteriores conservan el suyo. Moneda y mes
  de inicio no se cambian; una desactivada no se reactiva. Día 1 a 31; si el mes es más corto, vence
  el último día.
- **Pendientes y pago:** `list_pending_recurring(mes)` lista las plantillas activas desde su mes de
  inicio sin pago vigente en el mes, con vencimiento y marca de atrasado (hoy en
  `APP_TIMEZONE`), y los ya pagados; no convierte USD. El pago es `add_expense` con `recurring`
  (`F-n` o nombre): monto por defecto el de la plantilla para ese mes (se puede cambiar), bolsa y
  categoría por defecto las de la plantilla. Un solo pago vigente por plantilla y mes (índice único
  parcial `ux_expenses_recurring_month`, que ignora los anulados: anulado el pago, vuelve a
  pendiente). Un fijo en USD exige el tipo de cambio de ese pago; nunca se asume ni se reutiliza el
  último (decisión #12d).
- **Referencias:** `F-<n>` para gastos fijos (además de `I-<n>` y `G-<n>`).
- **Idempotencia:** `operation_id` obligatorio en `register_extra_income`, `confirm_allocation` (al
  confirmar), `add_expense` (también al pagar un fijo) y en `manage_recurring` al crear, actualizar
  y desactivar.
- **Libro mayor en la base (0005):** un reparto no vuelve a `pendiente` ni se hace sobre un ingreso
  anulado (la función `pp_ledger_movement_update` se reemplaza; el downgrade restaura la de 0004);
  `recurring_id` de un gasto no se edita; plantillas y montos no se borran.
- **Downgrade protegido:** `0005_extras_recurring` aborta si hay plantillas, extras o gastos
  enlazados, salvo con `ALLOW_DESTRUCTIVE_DOWNGRADE=true`. El upgrade se niega si encuentra un
  ingreso que no es extra en estado pendiente.
- **Registros:** sin montos, descripciones, orígenes de extras ni nombres de plantillas (solo
  referencias `I-`, `G-`, `F-`, mes, moneda y si hubo sobregasto).

### Bolsas flexibles y metas [DECIDIDO] (Hito 7)

- **Código:** `domain/rebalance.py` (reajuste puro: proporcional, desde una bolsa, manual),
  `domain/goals.py` (estados, avance, `reached`, variación neta del RN-28), validaciones nuevas en
  `domain/pockets.py`; `services/flex.py` y `services/goals.py` (mixins de `LedgerService`);
  `mcp/pockets_tools.py`. Migración `0006_pockets_goals`.
- **Reajuste (RN-13, RN-14, RN-17, RN-01):** función pura sobre los porcentajes vigentes del mes
  objetivo (propios o heredados, RN-03). Proporcional con enteros hacia abajo y el residuo en la
  última bolsa existente; nunca negativos, siempre suma 100 (prueba de propiedades con semilla fija).
  `preview_rebalance` no guarda nada y devuelve los porcentajes anteriores y nuevos.
- **Crear bolsa:** nombre único sin distinguir mayúsculas (también frente a las archivadas, índice
  `ux_pockets_name_ci`); crear la bolsa y escribir el conjunto completo de porcentajes del mes
  objetivo ocurre en una transacción (RN-13). Mes objetivo: el siguiente por defecto o el actual
  (RN-15), nunca uno pasado. **Lectura de "recalcular el mes en curso" (RN-15) [PROPUESTO]:** nada
  recalcula repartos guardados (cada reparto guarda el porcentaje que usó); aplicar en el mes actual
  solo cambia los porcentajes para lo que se reparta desde ese momento. Los meses futuros que ya
  tienen porcentajes propios no cambian (la bolsa nueva queda en 0 % en ellos) y la respuesta los
  lista.
- **Archivar bolsa (RN-16 a RN-18):** solo con saldo (acumulable) o disponible del mes (consumo)
  cero; nunca se borra (`active = FALSE`, `archived_at`). Es inmediato: en la misma transacción
  reescribe sin ella los porcentajes del mes actual (propios o heredados) y de cada mes futuro con
  porcentajes propios, con la estrategia elegida, así ningún mes de ahora en adelante reparte a una
  bolsa inactiva ni suma distinto de 100. Sus metas quedan con `archived_at`. No se reactiva. Para
  vaciar una bolsa con saldo hace falta una transferencia (Hito 8).
- **Bolsa archivada en las tools anteriores [PROPUESTO]:** rechaza gastos, pagos de fijos, repartos
  de salario y de extras, porcentajes, categorías y metas nuevas (las búsquedas por nombre solo ven
  bolsas activas), y `void_transaction` rechaza anular un movimiento que toque una bolsa archivada
  (cambiaría un saldo que debe quedar en cero).
- **Metas (RN-19 a RN-25):** solo en bolsas acumulables activas; una sola meta activa por bolsa
  (índice único parcial `ux_savings_goals_active_pocket` y validación en el código). Sin dinero
  propio: el avance es `accumulated_balance` (11.2), la misma función de `get_bolsa_status`; crear o
  cambiar una meta no mueve saldos. Referencia pública `M-<n>`.
- **Lograda (RN-24):** `domain.goals.reached` decide; los almacenes la llaman (`_settle_goals`) en
  la transacción de cada operación que sube un saldo: salario, saldo inicial, reparto de un extra,
  anular un gasto, crear una meta y cambiarla. Fecha de logro: la del movimiento que cruzó el
  objetivo (fecha del ingreso; hoy para el reparto de un extra o una anulación), nunca anterior a la
  creación de la meta. Permanece lograda aunque el saldo baje, también si se anula el movimiento que
  la cruzó [PROPUESTO]. Si al crearla el saldo ya alcanza el objetivo, nace lograda [PROPUESTO].
- **RN-28:** `get_goal_progress` entrega el promedio mensual de la variación neta del saldo
  (asignado con ese mes presupuestario − gastado ese mes calendario) de los últimos 3 meses completos
  desde el primero con movimientos, y `projectable` (al menos un mes y promedio positivo). La
  proyección la hace Claude. El excedente (RN-29) se informa y se queda en la bolsa.
- **Confirmación:** `create_bolsa` y `archive_bolsa` siguen el patrón de `confirm_allocation`
  (vista previa con `preview_token`, aprobación explícita, `confirm=true`). La nota del Hito 6 sigue
  valiendo: `confirm=true` no garantiza por sí solo que el modelo haya preguntado; la ficha, las
  instrucciones del servidor y el permiso por tool del cliente lo mitigan.
- **Idempotencia:** `operation_id` en `create_bolsa` y `archive_bolsa` (al confirmar),
  `create_goal` y `update_goal`.
- **Base (0006):** disparadores: una bolsa no se borra, no se reactiva ni cambia de comportamiento;
  una meta no se borra, no cambia de bolsa, nombre ni fecha de creación; una lograda no cambia de
  estado, fecha de logro ni objetivo; una archivada no cambia.
- **Downgrade protegido:** `0006_pockets_goals` aborta si hay metas o bolsas archivadas, salvo con
  `ALLOW_DESTRUCTIVE_DOWNGRADE=true`.
- **Registros:** sin montos, porcentajes ni nombres de metas (solo `M-n`, comportamiento y meses).

### Transferencias [DECIDIDO] (Hito 8)

- **Código:** `domain/transfers.py` (motivos, nota, monto, fecha, `T-n`, RN-41, RN-42, efecto en
  metas de RN-58), `domain/balances.py` (`TransferEntry` y `pocket_figures`), `services/transfers.py`
  (mixin de `LedgerService`), `mcp/transfers_tools.py`. Migración `0007_transfers`.
- **Una sola función de cálculo (9.1, 11.1, 11.2):** `pocket_figures` devuelve presupuesto original
  (asignado), recibidas y enviadas del mes, presupuesto ajustado (asignado + recibidas − enviadas),
  gastado, disponible (consumo) o saldo histórico con todas las transferencias (acumulable), y el %
  usado sobre el ajustado con el % sobre el original como referencia [PROPUESTO]. La usan
  `get_bolsa_status`, `get_summary`, `get_allocation_context`, `list_bolsas`, la advertencia de
  sobregasto (RN-37), las vistas previas, RN-18 y RN-42. El avance de las metas y la variación neta
  del RN-28 incluyen las transferencias.
- **Flujo:** `preview_transfer` no guarda nada y devuelve ambas bolsas antes y después (saldo, o
  disponible y presupuesto ajustado del mes) y el efecto en la meta activa de cada una (RN-58: % antes
  y después, faltante y si la completaría). `transfer_between_bolsas` sin `confirm=true` devuelve la
  misma vista previa; con `confirm=true` exige `operation_id` y el `preview_token` (huella SHA-256 de
  origen, destino, monto, motivo, nota y fecha).
- **Validaciones:** monto entero positivo en colones (sin texto ni decimales) y origen distinto del
  destino (RN-41); bolsas activas por nombre sin distinguir mayúsculas; no más de lo disponible en el
  origen y nunca desde una bolsa en negativo (RN-42); motivo `cubrir_sobregasto`, `reasignacion` o
  `ajuste` (`cierre_de_mes` es solo de `close_month`: la tool lo rechaza); nota de hasta 140; fecha
  siempre hoy en `APP_TIMEZONE` (`transfer_date` opcional, solo la de hoy) [PROPUESTO] y mes de esa
  fecha; un mes cerrado no admite transferencias (RN-44, Hito 9).
- **Atomicidad y concurrencia:** una transacción bloquea las dos filas de `pockets` con
  `SELECT … FOR UPDATE` en orden de id (sin interbloqueos entre transferencias cruzadas), vuelve a
  leer sus movimientos y valida RN-41/RN-42 otra vez antes del INSERT; en la misma transacción evalúa
  las metas (`_settle_goals`, RN-24) y guarda la clave de operación. `archive_bolsa` también bloquea
  su bolsa y vuelve a comprobar el saldo cero (RN-18), así una transferencia simultánea no la deja
  archivada con dinero. Probado contra Postgres con un retardo dentro de la transacción.
- **Inmutabilidad (RN-43, principio 3.4) [PROPUESTO]:** CHECK (monto > 0, origen ≠ destino, motivo
  permitido incluido el reservado, mes `YYYY-MM`, nota ≤ 140), claves foráneas ON DELETE RESTRICT y
  disparador `trg_transfers_immutable` que rechaza UPDATE y DELETE. No hay tools para anular ni
  editar: `void_transaction("T-n")` explica que se corrige con una transferencia inversa.
- **Referencias:** `T-<n>`. `list_transactions` admite `type = transferencia` y el filtro por bolsa
  (origen o destino); el límite por defecto y el máximo no cambian.
- **Sobregasto (RN-37):** `available_pockets` y la advertencia usan `pocket_figures`; las
  descripciones guían a Claude: proponer una transferencia con `preview_transfer`, esperar la
  aprobación explícita y solo entonces confirmar. La nota del Hito 6 sigue valiendo: `confirm=true` no
  garantiza por sí solo que el modelo haya preguntado; la ficha, las instrucciones del servidor y el
  permiso por tool del cliente lo mitigan.
- **Archivar (RN-18):** con saldo o disponible del mes distinto de cero (también negativo), el error
  indica mover primero el dinero con una transferencia (motivo `reasignacion`), sin montos.
- **Idempotencia:** `operation_id` en `transfer_between_bolsas` (al confirmar).
- **Downgrade protegido:** `0007_transfers` aborta si hay transferencias, salvo con
  `ALLOW_DESTRUCTIVE_DOWNGRADE=true`.
- **Registros:** sin montos, notas, nombres de bolsas ni de metas (solo `T-n`, mes, motivo y cuántas
  metas se afectaron). La nota se ve en la respuesta y en `list_transactions`.

### Cierre de mes [DECIDIDO] (Hito 9)

- **Código:** `domain/closures.py` (regla única de mes cerrado, qué mes se cierra, cierre pendiente,
  datos del mes, validación de la propuesta y resultado), `domain/balances.py` (`integrity_gap` con
  meses cerrados y ajustes), `services/closing.py` (mixin `ClosingMixin` de `LedgerService`),
  `mcp/closing_tools.py`. Migración `0008_month_closures`.
- **Una sola regla de mes cerrado (RN-44, RN-48, RN-53):** `domain.closures.is_closed`: un mes está
  cerrado si tiene su cierre guardado o es anterior o igual al último mes cerrado. Un mes sin fila
  (y posterior al último cerrado) está abierto. La usan los servicios para fallar temprano
  (`_ensure_open`) y el almacén dentro de cada transacción de escritura (`_guard_months`). Aplica a
  gastos (mes calendario), ingresos, saldo inicial y extras (mes presupuestario), repartos de extras
  y anulaciones (mes del movimiento), transferencias (su mes) y porcentajes (el mes escrito por
  `set_allocation`, `create_bolsa` y `archive_bolsa`). Errores sin montos ni notas.
- **Qué mes se cierra [PROPUESTO]:** desde su último día (hoy en `APP_TIMEZONE` ≥ último día), en
  orden estricto de meses consecutivos: el primero cerrable es el siguiente al último cerrado o, sin
  cierres, el más antiguo con movimientos (ingresos de cualquier tipo o estado, gastos incluidos los
  anulados, transferencias). Un mes vacío en medio también se cierra (cierre trivial). Ya cerrado,
  futuro, fuera de orden o anterior al primero con movimientos: error claro sin montos. Extras
  pendientes del mes (RN-09) bloquean; fijos pendientes solo avisan.
- **Vista previa (principio 3.2):** `preview_month_close` sin propuesta devuelve datos (11.1 por
  bolsa de consumo: sobrante o déficit; 11.2 por acumulable: saldo y meta activa; extras y fijos
  pendientes; destino sugerido, 6.5). Con propuesta valida y devuelve cómo queda cada bolsa, el
  efecto en las metas (RN-58), el sobrante no destinado y el sobregasto no cubierto, las
  transferencias a crear y la ficha. Siempre avisa que el mes no admitirá más movimientos, ni de
  hoy. La app no recomienda (principio 3.1).
- **Validación (10.1, 10.2, RN-47, RN-50, RN-52):** déficit y sobrante solo en bolsas de consumo
  activas (una acumulable en negativo se avisa con el camino para corregirla: una transferencia hacia
  ella). Cobertura: hacia una de consumo con déficit, sin cubrir de más, desde un sobrante de consumo
  o desde el saldo positivo de una acumulable. Destino: desde un sobrante de consumo hacia una
  acumulable activa o `null` (no destinado). Lo que sale de una bolsa no supera su sobrante o saldo.
  Orden fijo: mientras quede un déficit sin cubrir, o si una cobertura sale de una acumulable, todo
  el sobrante de consumo va a coberturas. La cobertura desde acumulable es opcional: sin ella, lo
  restante queda como sobregasto no cubierto y el mes se cierra igual. Montos enteros JSON; pares
  repetidos y bolsas archivadas o inexistentes se rechazan. Una archivada con cifras en el mes se
  lista y su resto va entero a ajustes.
- **Ficha:** SHA-256 en dos mitades: la propuesta (mes, ids, montos) y una instantánea del estado
  (cifras de cada bolsa, metas activas, extras pendientes). Otra propuesta o sin ficha: "pide la
  vista previa"; misma propuesta con el estado cambiado: "el estado cambió, repite la vista previa".
- **Atomicidad y concurrencia (RN-46):** `record_closure` en una transacción: bloqueo consultivo de
  cierres exclusivo (`pg_advisory_xact_lock(0x5050, 0)`), `FOR UPDATE` de todas las bolsas en orden
  de id, nueva lectura y recálculo completo (si la ficha no coincide, no se guarda nada), fila de
  `month_closures`, transferencias `cierre_de_mes` (fecha hoy, mes el cerrado, sin nota), ajustes,
  `_settle_goals` con hoy y la clave de operación. Las escrituras que tocan un mes toman el mismo
  bloqueo en modo compartido antes de bloquear bolsas o escribir (siguen en paralelo entre sí): un
  gasto que llega durante el cierre espera y se rechaza por mes cerrado; si entró antes, el cierre
  pide repetir la vista previa. Un solo bloqueo global (no uno por mes) porque cerrar M cierra todos
  los meses ≤ M. Orden "guardia, bolsas, filas" en todas las rutas: sin interbloqueos (probado con
  gasto, transferencia y cierre simultáneos).
- **Mes actual cerrado (cierre hecho el último día) [PROPUESTO]:** `set_allocation` de ese mes se
  rechaza; `create_bolsa` y `archive_bolsa` aplican desde el primer mes abierto y lo dicen en la
  vista previa (RN-18 de consumo se comprueba en ese mes). Archivar una acumulable la quita como
  destino sugerido de las bolsas que la tenían.
- **Consultas:** `get_summary` y `list_bolsas` traen `pending_closure` (RN-49: meses terminados sin
  cerrar desde el primero cerrable, con `has_movements`); `get_summary` y `get_bolsa_status` de un
  mes cerrado traen `month_closed` y sus ajustes (RN-50).
- **Ritual (RN-51):** las instrucciones del servidor lo explican: `preview_month_close`, propuesta de
  Claude con explicación breve, aprobación explícita, `close_month` y luego el salario del mes
  siguiente y los porcentajes si cambian. La nota del Hito 6 sigue valiendo: `confirm=true` no
  garantiza por sí solo que el modelo haya preguntado.
- **Destino sugerido (6.5):** `set_surplus_destination` escribe `pockets.surplus_target_pocket_id`
  (columna de 0003, reutilizada): bolsa de consumo activa, destino acumulable activa o `null`.
- **Sin reapertura (RN-48) [PROPUESTO]:** no hay tool para reabrir ni borrar cierres; disparadores
  `trg_month_closures_guard` (no se borra ni sale de `cerrado`, ni cambia mes o instante) y
  `trg_closure_adjustments_immutable` (sin UPDATE ni DELETE). Una corrección posterior es una
  transferencia `ajuste` o un movimiento nuevo en un mes abierto (README).
- **Transferencias (0008):** CHECK `ck_transfers_month_date`: el mes es el de la fecha, salvo
  `cierre_de_mes`, cuyo mes es el cerrado y nunca posterior al de la fecha. El upgrade comprueba
  antes los datos.
- **Idempotencia:** `operation_id` en `close_month` (al confirmar) y `set_surplus_destination`.
- **Downgrade protegido:** `0008_month_closures` aborta si hay cierres o ajustes, salvo con
  `ALLOW_DESTRUCTIVE_DOWNGRADE=true`.
- **Registros:** sin montos, notas, nombres de bolsas ni de metas (solo mes y cuántas
  transferencias, ajustes y metas afectadas).

---

## 12. Integración con Claude (MCP)

### 12.1 Catálogo de tools

| Tool | Función | Estado |
|---|---|---|
| `preview_initial_balance` | Vista previa del saldo inicial (total y monto por bolsa) sin guardar nada (principio 3.2). | [DECIDIDO] (Hito 4) |
| `load_initial_balance` | Cargar el saldo inicial repartido por montos entre bolsas (una sola vez). | [DECIDIDO] |
| `list_bolsas` | Listar las bolsas activas con su comportamiento y su saldo (acumulable, 11.2) o disponible del mes actual (consumo, 11.1), y los meses con cierre pendiente (RN-49). | [DECIDIDO] (Hito 4; cierre pendiente en el Hito 9) |
| `add_expense` | Registrar gasto (con moneda y, si es USD, tipo de cambio). Si deja una bolsa en negativo, devuelve advertencia con las bolsas disponibles. | [DECIDIDO] (Hito 5) |
| `preview_income` | Vista previa del salario: mes presupuestario y reparto por bolsa, sin guardar nada (principio 3.2). | [DECIDIDO] (Hito 5) |
| `add_income` | Registrar ingreso base (con moneda y tipo de cambio si aplica); exige `confirm=true`. | [DECIDIDO] (Hito 5) |
| `create_category` / `list_categories` | Crear y listar categorías de gasto con su bolsa por defecto. | [DECIDIDO] (Hito 5) |
| `register_extra_income` | Registrar ingreso extra en estado pendiente ("sin asignar"), en el mes de su fecha (RN-09). | [DECIDIDO] (Hito 6) |
| `get_allocation_context` | Entregar a Claude el panorama del mes: presupuesto original y ajustado vs gastado por bolsa, fijos pendientes, metas y repartos previos (solo agregados). | [DECIDIDO] (Hito 6; metas en el Hito 7; presupuesto ajustado en el Hito 8) |
| `confirm_allocation` | Confirmar el reparto de un extra (valida suma = 100). Sin `confirm` devuelve la vista previa y su `preview_token`; con `confirm=true` lo exige. | [DECIDIDO] (Hito 6) |
| `void_transaction` | Anular un ingreso o gasto con motivo, solo en mes abierto (regla única de mes cerrado, Hito 9); vista previa sin `confirm`. Reemplaza a `update_transaction` y `delete_transaction`. Las transferencias (`T-n`) no se anulan (RN-43). | [DECIDIDO] (Hito 5) |
| `get_bolsa_status` | Estado de una bolsa: asignado, transferencias, presupuesto ajustado, gastado, disponible con % usado (ajustado y original) y avance de su meta si la tiene. | [DECIDIDO] (Hito 5; meta en el Hito 7; transferencias en el Hito 8) |
| `get_summary(mes)` | Resumen mensual, con el presupuesto original y el ajustado de cada bolsa; si el mes está cerrado, sus ajustes; y los meses con cierre pendiente (RN-49). | [DECIDIDO] (Hito 5; ajustado en el Hito 8; cierre en el Hito 9) |
| `top_categories` | En qué se gasta más. | [DECIDIDO] (Hito 5) |
| `list_transactions` | Listar movimientos con filtros (20 por defecto, máximo 100), incluidas las transferencias (`T-n`). | [DECIDIDO] (Hito 5; transferencias en el Hito 8) |
| `manage_recurring` | Crear, listar, modificar y desactivar gastos fijos (nunca se borran). | [DECIDIDO] (Hito 6) |
| `list_pending_recurring` | Gastos fijos pendientes del mes (con vencimiento y atraso) y los ya pagados; el pago es `add_expense` con `recurring`. | [DECIDIDO] (Hito 6) |
| `set_allocation` / `update_allocation` | Cambiar porcentajes de un mes. | [DECIDIDO] |
| `get_allocation` | Consultar los porcentajes de un mes; si no tiene, los del mes anterior más cercano indicando su origen (RN-03). | [DECIDIDO] (Hito 4) |
| `preview_rebalance` | Calcular reajuste de porcentajes sin guardar. | [DECIDIDO] (Hito 7) |
| `create_bolsa` | Crear bolsa y reajustar porcentajes (atómico). | [DECIDIDO] (Hito 7) |
| `archive_bolsa` | Archivar bolsa (exige saldo cero, mediante transferencia previa) y redistribuir porcentaje. | [DECIDIDO] (Hito 7; vaciar con transferencia en el Hito 8) |
| `create_goal` | Crear meta asociada a una bolsa acumulable. | [DECIDIDO] (Hito 7) |
| `get_goal_progress` | Avance, faltante, %, excedente y los números del RN-28 (la fecha estimada la calcula Claude). | [DECIDIDO] (Hito 7) |
| `update_goal` | Cambiar monto o fecha, pausar o reactivar. | [DECIDIDO] (Hito 7) |
| `preview_transfer` | Simular movimiento entre bolsas (con aviso de efecto en metas, RN-58); devuelve la ficha. | [DECIDIDO] (Hito 8) |
| `transfer_between_bolsas` | Registrar movimiento entre bolsas (vista previa sin `confirm`; con `confirm=true` exige la ficha). | [DECIDIDO] (Hito 8) |
| `preview_month_close` | Datos del cierre de un mes (déficits, sobrantes, saldos y metas, extras y fijos pendientes, destino sugerido) y, con la propuesta de Claude, el resultado y la ficha; no guarda nada. | [DECIDIDO] (Hito 9) |
| `close_month` | Ejecutar el cierre (atómico): transferencias `cierre_de_mes`, ajustes, metas y marca de cerrado; vista previa sin `confirm`; con `confirm=true` exige la ficha. | [DECIDIDO] (Hito 9) |
| `set_surplus_destination` | Fijar o quitar el destino de sobrante sugerido de una bolsa de consumo (6.5). | [DECIDIDO] (Hito 9) |

**Tools eliminadas en v0.2:** `contribute_to_goal`, `withdraw_from_goal`, `spend_from_goal`, `update_transaction`, `delete_transaction`. Las metas ya no reciben ni entregan dinero por separado (sección 7), y las correcciones se hacen por anulación (RN-53).

### 12.2 Reglas para las tools
1. Las tools devuelven datos exactos y validan reglas. No dan consejos.
2. Las tools que modifican dinero deben ser **idempotentes** o aceptar una clave de operación, para que una llamada repetida por Claude no duplique un movimiento. **[DECIDIDO] (Hito 5):** `operation_id` obligatorio en `add_income` (al confirmar), `add_expense` y `void_transaction`; misma clave y mismo contenido devuelven la respuesta original, otro contenido es error. **(Hito 6):** también en `register_extra_income`, `confirm_allocation` (al confirmar) y `manage_recurring` (crear, actualizar, desactivar). **(Hito 7):** también en `create_bolsa` y `archive_bolsa` (al confirmar), `create_goal` y `update_goal`. **(Hito 8):** también en `transfer_between_bolsas` (al confirmar). **(Hito 9):** también en `close_month` (al confirmar) y `set_surplus_destination`.
3. Las tools destructivas o de reparto piden confirmación del usuario antes de ejecutarse.
4. Las respuestas de error deben ser claras para que Claude pueda explicarlas.
5. Toda tool que reciba un monto en dólares exige el tipo de cambio (RN-57). Si falta, devuelve error en lugar de asumirlo. Esto incluye el pago de un gasto fijo en USD (decisión #12d): nunca se reutiliza el último tipo de cambio.

---

## 13. Estadísticas y dashboard **[DECIDIDO en intención; detalle PROPUESTO]**

### 13.1 Preguntas que debe responder
- ¿En qué gasto más?
- ¿Cuánto de cada bolsa llevo gastado este mes (% del presupuesto)?
- ¿Cuánto he ingresado al ahorro, y de dónde vino (asignación mensual, extras, sobrantes de cierre)?
- ¿Cuánto ingreso tengo en el mes? (sin contar el saldo inicial)
- ¿Cuáles son mis gastos necesarios y cuáles son fijos?
- ¿Cómo voy en cada meta?

### 13.2 Componentes
- Tarjetas: ingreso del mes, gastado, disponible, ahorrado, ingresos **sin asignar**.
- Barras de progreso por bolsa (usado vs. presupuesto ajustado, con el original como referencia).
- Dona de gasto por categoría.
- Evolución mensual (línea o barras).
- Tabla de últimos movimientos con filtros (los anulados se distinguen visualmente).
- Lista de gastos fijos: pagados y pendientes.
- Tarjeta por meta: barra de progreso basada en el saldo de su bolsa, "faltan ₡X" y fecha estimada.
- Alertas: bolsa por encima de 80 % y 100 %, bolsa en negativo (rojo), cierre de mes pendiente, ingreso pendiente de repartir.
- Totales en colones, con equivalente en dólares opcional.


## 15. Requerimientos no funcionales

- **Privacidad:** Los datos se almacenan en el servidor del propietario. Al usar Claude mediante MCP, la información consultada y registrada transita por Cloudflare y Anthropic, y el propietario acepta ese tránsito. Las tools devuelven solo la información necesaria para cada consulta (minimización).
- **Autenticación:** el endpoint del MCP y el dashboard requieren token o login, aunque sea uso personal.
- **Respaldo:** copia automática y periódica de la base de datos.
- **Simplicidad de uso:** registrar un gasto debe tomar una sola frase a Claude.
- **Liviandad:** debe correr cómodamente en el hardware del homelab (laptop vieja, pocos recursos). Postgres corre en Docker; su consumo de memoria se mide con `docker stats` desde el Hito 1.
- **Calidad:** el invariante de la sección 11.4, las validaciones de sumas (porcentajes = 100) y la conversión de monedas deben estar cubiertos por tests automáticos.

---

## 16. Arquitectura propuesta **[PROPUESTO]**

```
Claude (chat) ──► Servidor MCP ──► PostgreSQL ◄── API ◄── Dashboard (React)
                  (tools)          (datos)
```

- **Base de datos:** PostgreSQL en un contenedor Docker, con volumen persistente.
- **MCP:** en Python, remoto por HTTPS mediante un túnel de Cloudflare (decisiones 9 y 10). El servidor de autorización de OAuth se decide en el Hito 3.
- **Dashboard:** React + Vite + TypeScript + Tailwind, con una librería de gráficos (por ejemplo Recharts).
- **Ejecución:** en el homelab del propietario.

---

## 17. Esquema de datos de referencia (v0.3, borrador, PostgreSQL)

Consolida y reemplaza los borradores anteriores. Es una propuesta técnica: puede ajustarse al implementar, siempre que respete las reglas de este documento.

Convenciones de tipos: identificadores y montos en `BIGINT`; banderas en `BOOLEAN`; fechas de calendario en `DATE`; instantes en `TIMESTAMPTZ`; el mes se guarda como texto de 7 caracteres `'YYYY-MM'` con un `CHECK` de formato.

```sql
-- Bolsas (Hito 4, migración 0003). "Bolsa" = pocket en el código
CREATE TABLE pockets (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- también fija el orden de creación (RN-08)
  name TEXT NOT NULL,                                  -- único sin distinguir mayúsculas (índice abajo)
  behavior TEXT NOT NULL CHECK (behavior IN ('consumo','acumulable')),
  group_name TEXT,                                     -- opcional, solo estadísticas
  surplus_target_pocket_id BIGINT REFERENCES pockets(id),  -- opcional; debe ser acumulable (se valida en código)
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  archived_at TIMESTAMPTZ,                              -- Hito 7 (0006): cuándo se archivó (RN-16)
  CHECK (active = (archived_at IS NULL))
);
-- Disparadores (0006): no se borra, no se reactiva, no cambia de comportamiento

CREATE UNIQUE INDEX ux_pockets_name_ci ON pockets (lower(name));

CREATE TABLE categories (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name TEXT NOT NULL,
  pocket_id BIGINT NOT NULL REFERENCES pockets(id),
  active BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE UNIQUE INDEX ux_categories_name_ci ON categories (lower(name));

-- Porcentajes por mes (historial). La app valida que cada mes sume 100 (RN-01).
CREATE TABLE budget_month_allocations (
  month CHAR(7) NOT NULL CHECK (month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),  -- 'YYYY-MM'
  pocket_id BIGINT NOT NULL REFERENCES pockets(id),
  percentage INTEGER NOT NULL CHECK (percentage BETWEEN 0 AND 100),
  PRIMARY KEY (month, pocket_id)
);

-- Ingresos (incluye el saldo inicial como registro especial). Hito 4 (0003) + Hito 5 (0004).
CREATE TABLE incomes (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  income_date DATE NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('base','extra','saldo_inicial')),
  source TEXT,
  budget_month CHAR(7) NOT NULL                        -- salario de fin de mes -> mes siguiente
    CHECK (budget_month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  amount BIGINT NOT NULL CHECK (amount > 0),           -- colones (base de todos los cálculos)
  allocation_status TEXT NOT NULL DEFAULT 'pendiente'
    CHECK (allocation_status IN ('pendiente','repartido')),
  -- Hito 6 (0005): solo un extra puede estar pendiente; source = origen del extra (hasta 120)
  CHECK (kind = 'extra' OR allocation_status = 'repartido'),
  note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- Hito 5 (0004): las filas existentes quedan en CRC con original_amount = amount
  currency TEXT NOT NULL DEFAULT 'CRC' CHECK (currency IN ('CRC','USD')),
  original_amount BIGINT NOT NULL CHECK (original_amount > 0),  -- CRC: colones; USD: centavos
  exchange_rate BIGINT,                                -- colones por USD x100; NULL si CRC
  voided BOOLEAN NOT NULL DEFAULT FALSE,
  voided_at TIMESTAMPTZ,
  void_reason TEXT,
  CHECK ((currency = 'CRC' AND exchange_rate IS NULL AND original_amount = amount)
      OR (currency = 'USD' AND exchange_rate IS NOT NULL AND exchange_rate > 0)),
  CHECK ((NOT voided AND voided_at IS NULL AND void_reason IS NULL)
      OR (voided AND voided_at IS NOT NULL AND void_reason IS NOT NULL
          AND char_length(void_reason) BETWEEN 3 AND 200))
);
-- Un solo saldo inicial vigente (RN-54); tras anularlo se permite otra carga
CREATE UNIQUE INDEX ux_incomes_single_initial_balance
  ON incomes (kind) WHERE kind = 'saldo_inicial' AND NOT voided;

-- Reparto de cada ingreso por bolsa
CREATE TABLE income_allocations (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  income_id BIGINT NOT NULL REFERENCES incomes(id),
  pocket_id BIGINT NOT NULL REFERENCES pockets(id),
  percentage INTEGER CHECK (percentage BETWEEN 0 AND 100),  -- NULL en el saldo inicial (monto explícito)
  amount BIGINT NOT NULL CHECK (amount >= 0),          -- colones; la última bolsa absorbe el residuo
  UNIQUE (income_id, pocket_id)
);

-- Metas: objetivo asociado a una bolsa acumulable. No guardan dinero ni avance (RN-23).
-- Hito 7, migración 0006. Referencia pública M-<id>
CREATE TABLE savings_goals (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  pocket_id BIGINT NOT NULL REFERENCES pockets(id),     -- acumulable y activa (se valida en código)
  name TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 60),
  target_amount BIGINT NOT NULL CHECK (target_amount > 0),  -- en colones (RN-19)
  target_date DATE,                                    -- opcional (RN-20)
  status TEXT NOT NULL DEFAULT 'activa'
    CHECK (status IN ('activa','lograda','pausada')),
  achieved_on DATE,                                    -- se llena al pasar a 'lograda' (RN-24)
  created_on DATE NOT NULL,
  archived_at TIMESTAMPTZ,                             -- se archivó junto con su bolsa (6.4)
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK ((status = 'lograda') = (achieved_on IS NOT NULL))
);
-- Una sola meta activa por bolsa (RN-22, decisión #11 resuelta)
CREATE UNIQUE INDEX ux_savings_goals_active_pocket
  ON savings_goals (pocket_id) WHERE status = 'activa' AND archived_at IS NULL;
-- Disparadores (0006): sin DELETE; bolsa, nombre y creación no cambian; lograda y archivada fijas

-- Gastos (Hito 5, migración 0004). Referencia pública G-<id>
CREATE TABLE expenses (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  expense_date DATE NOT NULL,                          -- no futura (se valida en código)
  month CHAR(7) NOT NULL                               -- mes calendario de la fecha (RN-32)
    CHECK (month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  pocket_id BIGINT NOT NULL REFERENCES pockets(id),
  category_id BIGINT REFERENCES categories(id),        -- NULL = "pendiente de clasificar" (RN-34)
  description TEXT CHECK (description IS NULL OR char_length(description) <= 120),
  currency TEXT NOT NULL DEFAULT 'CRC' CHECK (currency IN ('CRC','USD')),
  original_amount BIGINT NOT NULL CHECK (original_amount > 0),
  exchange_rate BIGINT,
  amount BIGINT NOT NULL CHECK (amount > 0),           -- equivalente en colones
  voided BOOLEAN NOT NULL DEFAULT FALSE,
  voided_at TIMESTAMPTZ,
  void_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  recurring_id BIGINT REFERENCES recurring_expenses(id),  -- Hito 6: pago de un gasto fijo
  -- mismos CHECK de moneda y anulación que incomes
);
CREATE INDEX ix_expenses_month ON expenses (month);
CREATE INDEX ix_expenses_pocket_month ON expenses (pocket_id, month);
-- Un solo pago vigente por gasto fijo y mes (anulado, el fijo vuelve a pendiente)
CREATE UNIQUE INDEX ux_expenses_recurring_month ON expenses (recurring_id, month)
  WHERE recurring_id IS NOT NULL AND NOT voided;

-- Claves de operación (idempotencia, regla 12.2.2). Hito 5, migración 0004
CREATE TABLE idempotency_keys (
  operation_id TEXT PRIMARY KEY CHECK (char_length(operation_id) BETWEEN 8 AND 100),
  tool TEXT NOT NULL,
  fingerprint CHAR(64) NOT NULL,                       -- SHA-256 del contenido normalizado
  response JSONB NOT NULL,                             -- respuesta original, devuelta tal cual
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Disparadores del libro mayor (0004): sin DELETE en incomes, income_allocations y expenses; sin
-- UPDATE en income_allocations; en incomes y expenses solo se permite anular (no deshacer).

-- Gastos fijos mensuales (plantillas). Hito 6, migración 0005. Referencia pública F-<id>
CREATE TABLE recurring_expenses (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 60),
  currency TEXT NOT NULL CHECK (currency IN ('CRC','USD')),   -- no se cambia (disparador)
  day_of_month INTEGER NOT NULL CHECK (day_of_month BETWEEN 1 AND 31),  -- mes corto: último día
  pocket_id BIGINT NOT NULL REFERENCES pockets(id),     -- bolsa por defecto del pago
  category_id BIGINT REFERENCES categories(id),         -- opcional
  start_month CHAR(7) NOT NULL CHECK (start_month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),  -- no se cambia
  active BOOLEAN NOT NULL DEFAULT TRUE,                 -- nunca se borra; no se reactiva
  deactivated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (active = (deactivated_at IS NULL))
);
CREATE UNIQUE INDEX ux_recurring_expenses_name_active ON recurring_expenses (lower(name))
  WHERE active;

-- Monto de cada plantilla desde un mes: cambiarlo afecta solo meses futuros. Sin tipo de cambio:
-- cada pago en USD trae el suyo (decisión #12d)
CREATE TABLE recurring_expense_amounts (
  recurring_id BIGINT NOT NULL REFERENCES recurring_expenses(id),
  from_month CHAR(7) NOT NULL CHECK (from_month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  original_amount BIGINT NOT NULL CHECK (original_amount > 0),  -- CRC: colones; USD: centavos
  PRIMARY KEY (recurring_id, from_month)
);

-- Registro de transferencias entre bolsas (inmutable; siempre en colones). Hito 8, migración 0007.
-- Referencia pública T-<id>
CREATE TABLE transfers (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  transfer_date DATE NOT NULL,                         -- siempre hoy (APP_TIMEZONE)
  month CHAR(7) NOT NULL                               -- mes de la fecha (presupuestario)
    CHECK (month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  from_pocket_id BIGINT NOT NULL REFERENCES pockets(id) ON DELETE RESTRICT,
  to_pocket_id BIGINT NOT NULL REFERENCES pockets(id) ON DELETE RESTRICT,
  amount BIGINT NOT NULL CHECK (amount > 0),           -- colones (RN-41)
  reason TEXT NOT NULL CHECK (reason IN
    ('cubrir_sobregasto','reasignacion','cierre_de_mes','ajuste')),  -- cierre_de_mes: Hito 9
  note TEXT CHECK (note IS NULL OR char_length(note) <= 140),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (from_pocket_id <> to_pocket_id)               -- RN-41
);
CREATE INDEX ix_transfers_month ON transfers (month);
CREATE INDEX ix_transfers_from_month ON transfers (from_pocket_id, month);
CREATE INDEX ix_transfers_to_month ON transfers (to_pocket_id, month);
-- Disparador (0007): trg_transfers_immutable rechaza UPDATE y DELETE (RN-43)
-- CHECK (0008): ck_transfers_month_date: month = mes de transfer_date, salvo 'cierre_de_mes'
--   (mes cerrado, nunca posterior al de la fecha)

-- Meses cerrados (Hito 9, migración 0008). Un mes sin fila cuenta como abierto (salvo que sea
-- anterior al último cerrado); la migración no cierra nada
CREATE TABLE month_closures (
  month CHAR(7) PRIMARY KEY CHECK (month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  status TEXT NOT NULL DEFAULT 'cerrado' CHECK (status IN ('abierto','cerrado')),
  closed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK ((status = 'cerrado') = (closed_at IS NOT NULL))
);
-- Disparador (0008): trg_month_closures_guard: sin DELETE; un mes cerrado no sale de 'cerrado' ni
-- cambia su mes o su instante (RN-48)

-- Sobrantes no destinados y sobregastos no cubiertos al cerrar (RN-50, 10.2). Hito 9, 0008
CREATE TABLE closure_adjustments (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  month CHAR(7) NOT NULL REFERENCES month_closures(month) ON DELETE RESTRICT,
  pocket_id BIGINT NOT NULL REFERENCES pockets(id) ON DELETE RESTRICT,
  kind TEXT NOT NULL CHECK (kind IN ('sobrante_no_destinado','sobregasto_no_cubierto')),
  amount BIGINT NOT NULL,                              -- con signo: sobrante +, sobregasto -
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK ((kind = 'sobrante_no_destinado' AND amount > 0)
      OR (kind = 'sobregasto_no_cubierto' AND amount < 0)),
  UNIQUE (month, pocket_id, kind)
);
-- Disparador (0008): trg_closure_adjustments_immutable rechaza UPDATE y DELETE
```

**Cambios en v0.3:** traducción técnica a PostgreSQL (sin `PRAGMA`; `BOOLEAN`, `DATE`/`TIMESTAMPTZ`, `BIGINT`; mes como `CHAR(7)` con `CHECK` de formato). No cambia ninguna regla.

**Cambios respecto a v0.1:** se eliminan `goal_movements` y los campos `goal_id` de `gastos` y `transfers` (la meta ya no tiene dinero propio); se agregan campos de moneda, anulación y saldo inicial; se agrega `fecha_logro` a las metas.

**Validaciones que viven en el código (no en el esquema):**
- Cada mes suma 100 % en `budget_month_allocations` (RN-01), con cada bolsa activa exactamente una vez.
- Las metas solo se asocian a bolsas `acumulable` y activas (RN-21).
- El reajuste de porcentajes al crear o archivar una bolsa deja cada mes afectado en exactamente 100 % entre bolsas activas (RN-01, RN-13, RN-17).
- Una bolsa archivada no recibe gastos ni repartos, y no se anulan movimientos que la toquen.
- No se transfiere más del saldo o disponible de la bolsa de origen, ni desde una bolsa en negativo
  (RN-42); se valida otra vez dentro de la transacción, con las dos bolsas bloqueadas.
- Una transferencia es entre dos bolsas activas, con la fecha de hoy; la tool no acepta el motivo
  `cierre_de_mes` (solo lo registra `close_month`).
- Un mes cerrado (o anterior al último cerrado) no admite movimientos, repartos, transferencias,
  anulaciones ni cambios de porcentajes (RN-44, RN-48, RN-53); lo decide `domain.closures.is_closed`
  y se comprueba otra vez dentro de la transacción, con el bloqueo de cierres compartido.
- Un mes se cierra desde su último día, en orden y sin extras pendientes; la propuesta cumple 10.1,
  10.2, RN-47 y RN-52, y se recalcula dentro de la transacción del cierre.
- Una bolsa solo se archiva con saldo (o disponible del mes) cero (RN-18), comprobado dentro de la
  transacción con la bolsa bloqueada.
- El saldo inicial se carga una sola vez mientras esté vigente (RN-54); anulado, se permite otra carga.
- La conversión USD → CRC usa el tipo de cambio indicado, dentro del rango configurado, y redondeo
  half-up; nunca da 0 colones (RN-57).
- Las fechas de gastos e ingresos no son futuras.
- Las operaciones compuestas (crear bolsa, cerrar mes, anular un ingreso ya repartido, repartir un extra) se ejecutan en una sola transacción.
- El reparto de un extra suma exactamente 100 % entre bolsas activas (RN-01, RN-07) y exige la ficha de su vista previa.
- Un pago de gasto fijo pertenece al mes calendario de su fecha y no puede ser anterior al mes de inicio de la plantilla.

---

## Concepto → tabla

La constitución habla en conceptos de negocio; esta tabla los lleva a las tablas y columnas del
esquema de la sección 17, con los valores que se guardan para estados, tipos y motivos.

| Concepto (constitución) | Tabla / columna | Valores que se guardan |
|---|---|---|
| Bolsa | `pockets` | — |
| Comportamiento de la bolsa (RN-10) | `pockets.behavior` | `consumo`, `acumulable` |
| Bolsa inactiva (archivada, RN-16) | `pockets.active`, `pockets.archived_at` | `TRUE` activa, `FALSE` archivada (con fecha) |
| Grupo de la bolsa | `pockets.group_name` | texto libre u omitido |
| Destino de sobrante sugerido (6.5) | `pockets.surplus_target_pocket_id` | id de una bolsa acumulable u omitido |
| Categoría | `categories` (`active`) | `TRUE`, `FALSE` |
| Los porcentajes de cada mes (RN-01 a 03) | `budget_month_allocations` (`month`, `pocket_id`, `percentage`) | `percentage` entero entre 0 y 100 |
| Ingreso | `incomes` | — |
| Tipo de ingreso: base, extra, saldo inicial (5.1, 5.3, RN-54) | `incomes.kind` | `base`, `extra`, `saldo_inicial` |
| Mes presupuestario (5.1, RN-09) | `incomes.budget_month` | `'YYYY-MM'` |
| Estado del reparto de un ingreso (RN-06) | `incomes.allocation_status` | `pendiente` (solo extras: "sin asignar"), `repartido` |
| Origen de un ingreso extra | `incomes.source` | texto corto opcional (hasta 120) |
| Moneda (RN-55) | `incomes.currency`, `expenses.currency`, `recurring_expenses.currency` | `CRC`, `USD` |
| Monto original y tipo de cambio (RN-57) | `original_amount`, `exchange_rate`, `amount` en `incomes` y `expenses` | CRC en colones; USD en centavos; tipo de cambio en colones por USD × 100; `amount` en colones |
| Lo asignado a la bolsa por los ingresos del mes (11.1) | `income_allocations.amount` (y `percentage`, el porcentaje usado) | colones enteros |
| Gasto | `expenses` | — |
| Mes calendario del gasto (RN-32) | `expenses.month` | `'YYYY-MM'` |
| Gasto pendiente de clasificar (RN-34) | `expenses.category_id` | `NULL` |
| Anulación con registro (RN-53) | `voided`, `voided_at`, `void_reason` en `incomes` y `expenses` | `voided`: `TRUE`, `FALSE` |
| Clave de operación (12.2.2) | `idempotency_keys` | `tool`: `add_income`, `add_expense`, `void_transaction`, `register_extra_income`, `confirm_allocation`, `manage_recurring`, `create_bolsa`, `archive_bolsa`, `create_goal`, `update_goal`, `transfer_between_bolsas`, `close_month`, `set_surplus_destination` |
| Gasto fijo mensual (8.1) | `recurring_expenses` (`active`) | `TRUE` activo, `FALSE` desactivado |
| Monto del gasto fijo por mes (8.1) | `recurring_expense_amounts` (`from_month`, `original_amount`) | CRC en colones; USD en centavos |
| Pago de un gasto fijo (RN-35) | `expenses.recurring_id` | id de la plantilla u omitido |
| Meta de ahorro (sección 7) | `savings_goals` (`pocket_id`, `target_amount`, `target_date`) | colones; fecha opcional |
| Estado de una meta (RN-24) | `savings_goals.status`, `achieved_on` | `activa`, `lograda` (con fecha de logro), `pausada` |
| Meta archivada con su bolsa (6.4) | `savings_goals.archived_at` | instante u omitido |
| El registro de transferencias (RN-40) | `transfers` (`transfer_date`, `month`, `from_pocket_id`, `to_pocket_id`, `amount`, `note`) | colones enteros; nota hasta 140 |
| Motivo de una transferencia (sección 9) | `transfers.reason` | `cubrir_sobregasto`, `reasignacion`, `cierre_de_mes` (solo `close_month`, con el mes cerrado), `ajuste` |
| Transferencias recibidas y enviadas del mes (9.1) | suma de `transfers.amount` por `to_pocket_id` / `from_pocket_id` y `month` | colones; se derivan, no se guardan |
| Estado del mes (RN-49) | `month_closures` (`month`, `status`, `closed_at`) | `cerrado` (sin fila = abierto, salvo si es anterior al último cerrado) |
| Ajustes de cierre (RN-50, 10.2) | `closure_adjustments` (`month`, `pocket_id`, `kind`, `amount`) | `kind`: `sobrante_no_destinado` (monto +), `sobregasto_no_cubierto` (monto −) |
| Cierre pendiente (RN-49) | se deriva de `month_closures` y de los meses con movimientos | meses terminados sin cerrar, desde el primero cerrable |

**Idioma de los nombres:** decidido en el Hito 1: inglés (ver "Convención de idioma"). Ya están en
inglés las tablas de los Hitos 4 a 6 (`pockets`, `categories`, `budget_month_allocations`, `incomes`,
`income_allocations`, `expenses`, `idempotency_keys`, `recurring_expenses`,
`recurring_expense_amounts`, `savings_goals`, Hito 7; `transfers`, Hito 8; `month_closures` y
`closure_adjustments`, Hito 9): ya no queda ninguna con el nombre del borrador. Los **valores** guardados (columna de la derecha) se mantienen como están.

---

## Registro de cambios

| Versión | Fecha | Cambio |
|---|---|---|
| 0.1 | 2026-11-09 | Primera versión: secciones 12, 13, 15, 16 y 17 del documento de origen v0.3, stack decidido, tabla concepto → tabla y enlace a `HITOS.md`. |
| 0.2 | 2026-11-09 | Decisiones del Hito 1 (clarificación de `specs/001-cimientos`): SDK `mcp==2.3.0` con `MCPServer`, Streamable HTTP desde el Hito 1, uv, PostgreSQL 18, alcance del CI, convención de idioma (inglés en código y base; español en documentación y mensajes), procedimiento para actualizar el SDK y medición de memoria. |
| 0.3 | 2026-11-09 | Cierre del Hito 1: Python 3.14 y uv 0.12.5 fijados, driver psycopg 3 en modo síncrono, confirmación del SDK al implementar, medición de memoria en el equipo de desarrollo, estructura del código y servicios de Compose. |
| 0.4 | 2026-11-09 | Hito 2: dominio `puropockets.space` y subdominio `mcp.puropockets.space`; túnel de Cloudflare como servicio de Compose (perfil `tunnel`, cloudflared 2026.10.3); hosts y orígenes públicos permitidos; reinicio automático y healthchecks. |
| 0.5 | 2026-11-09 | Hito 3: servidor de autorización OAuth propio (decisión pendiente resuelta), endpoints, clientes, duraciones, scopes, tablas `0002_oauth`, argon2, límite de intentos y revocación. |
| 0.6 | 2026-11-10 | Hito 4: `pocket` como nombre de "bolsa" en tablas y código (las tools conservan sus nombres); se agregan al catálogo `preview_initial_balance` (principio 3.2), `list_bolsas` y `get_allocation`; nombres en inglés de `pockets`, `categories`, `budget_month_allocations`, `incomes` e `income_allocations` en la sección 17 y en la tabla concepto → tabla (nombres únicos sin distinguir mayúsculas); `incomes` se crea en el Hito 4 sin moneda ni anulación (llegan en el Hito 5 con su propia migración) y con índice único para el saldo inicial; sección "Presupuesto (Hito 4)": `APP_TIMEZONE`, estructura del código, salvaguardas y pruebas. |
| 0.7 | 2026-11-10 | Hito 5: sección "Movimientos (Hito 5)" (montos sin `float`, conversión half-up, `USD_RATE_MIN`/`USD_RATE_MAX`, salario, gastos, anulación, referencias `I-`/`G-`, idempotencia, disparadores del libro mayor, downgrade protegido); esquema de la sección 17 con `incomes` completo, `expenses` e `idempotency_keys` (migración `0004_movements`); catálogo con `preview_income`, `create_category` y `list_categories`; regla 12.2.2 pasa a [DECIDIDO]; tabla concepto → tabla actualizada. |
| 0.8 | 2026-11-11 | Hito 6: sección "Extras y gastos fijos (Hito 6)" (extra pendiente y "sin asignar", contexto con solo agregados, reparto con ficha de vista previa, instrucciones del servidor, límite de `confirm=true` y su mitigación, plantillas con historial de monto, pendientes y pago enlazado, referencias `F-`, idempotencia, disparadores y downgrade protegido); esquema de la sección 17 con `recurring_expenses`, `recurring_expense_amounts`, `expenses.recurring_id` y las restricciones nuevas de `incomes` (migración `0005_extras_recurring`); catálogo con `list_pending_recurring`; reglas 12.2.2 y 12.2.5 ampliadas; tabla concepto → tabla actualizada. |
| 0.9 | 2026-11-11 | Hito 7: sección "Bolsas flexibles y metas (Hito 7)" (reajuste puro con prueba de propiedades, crear bolsa atómica con el conjunto completo del mes, lectura [PROPUESTO] de RN-15, archivado inmediato que reescribe el mes actual y los futuros, bolsa archivada en las tools anteriores, metas sin dinero propio con una sola fuente del saldo, evaluación centralizada de `lograda`, números del RN-28, confirmación con ficha, disparadores y downgrade protegido); esquema de la sección 17 con `pockets.archived_at` y `savings_goals` en inglés (migración `0006_pockets_goals`); catálogo y regla 12.2.2 actualizados; tabla concepto → tabla con metas y archivado. |
| 0.10 | 2026-11-11 | Hito 8: sección "Transferencias (Hito 8)" (una sola función de cálculo para 9.1, 11.1 y 11.2, vista previa con efecto en metas y ficha, validaciones, bloqueo de las dos bolsas y nueva validación dentro de la transacción, archivado con bloqueo, inmutabilidad en la base, referencias `T-`, sobregasto guiado hacia la transferencia, idempotencia, downgrade protegido y registros); esquema de `transfers` en inglés con ON DELETE RESTRICT, nota ≤ 140 e índices (migración `0007_transfers`); catálogo y regla 12.2.2 actualizados; validaciones y tabla concepto → tabla con transferencias. |
| 0.11 | 2026-11-11 | Hito 9: sección "Cierre de mes (Hito 9)" (regla única de mes cerrado usada por todas las escrituras y comprobada dentro de la transacción, qué mes se cierra y en qué orden, vista previa con datos y con propuesta, validación de 10.1, 10.2, RN-47, RN-50 y RN-52, ficha en dos mitades, transacción con bloqueo consultivo de cierres y bolsas bloqueadas, mes actual cerrado, cierre pendiente, ritual RN-51, destino sugerido 6.5, sin reapertura, CHECK del mes de las transferencias, idempotencia, downgrade y registros); esquema de `month_closures` y `closure_adjustments` en inglés (migración `0008_month_closures`); catálogo con `preview_month_close`, `close_month` y `set_surplus_destination`; regla 12.2.2, validaciones y tabla concepto → tabla actualizadas; se quitan las frases "hasta el Hito 9 todos los meses están abiertos". |
