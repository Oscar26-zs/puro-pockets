# Feature Specification: Acceso remoto sin datos

**Feature Branch**: `hito-2-acceso-remoto`

**Created**: 2026-11-09

**Status**: Draft

**Input**: User description (prompt del Hito 2 en `HITOS.md`): "El propietario quiere llamar a la tool `ping` de su servidor MCP desde Claude en el navegador y en el celular, estando fuera de su casa. El servidor corre en su homelab y se publica en una URL HTTPS fija con su propio dominio. En este hito no se maneja información financiera. Incluye pruebas automáticas que verifiquen los criterios de aceptación."

**Hito**: 2 (Acceso remoto sin datos), según `HITOS.md`.

## Clarifications

### Session 2026-11-09

Decisiones dadas por el propietario al iniciar el hito:

- Q: ¿Qué dominio y subdominio se usan? → A: Dominio `puropockets.space` (registrado en Namecheap); el MCP se publica en `mcp.puropockets.space`. No es un secreto.
- Q: ¿Quién hace los pasos manuales? → A: El propietario: nameservers en Namecheap, cuenta y túnel en Cloudflare, Docker en el homelab y conector en claude.ai. El proyecto deja esos pasos en orden en el README.
- Q: ¿Cómo corre el túnel y de dónde toma su credencial? → A: Como un servicio más de Docker Compose, con el token en la variable `CF_TUNNEL_TOKEN` del `.env`. En `.env.example` la variable va vacía. El token real nunca se pide, escribe ni imprime.
- Q: ¿El servidor MCP publica puertos al exterior? → A: No. Solo el túnel lo alcanza, por la red interna de Docker. Para pruebas locales sigue publicado en `127.0.0.1`.
- Q: ¿Qué expone el servidor en este hito? → A: Solo `ping`, sin datos ni autenticación.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Llamar a `ping` desde Claude fuera de casa (Priority: P1)

Con el servidor corriendo en el homelab, el propietario abre Claude en el celular usando datos
móviles (otra red) y le pide que llame a `ping`. Claude llega al servidor por la URL fija
`https://mcp.puropockets.space/mcp` y recibe el estado del servidor y de la base.

**Why this priority**: es el objetivo del hito y valida temprano lo más incierto (acceso remoto)
antes de manejar dinero.

**Independent Test**: desde un equipo fuera de la red de la casa, un cliente MCP llama a `ping` en
`https://mcp.puropockets.space/mcp` y recibe `{"server": "ok", "database": "ok", "detail": null}`.

**Acceptance Scenarios**:

1. **Given** el homelab con los servicios y el túnel corriendo, **When** Claude (navegador o celular
   con datos móviles) llama a `ping` por el conector, **Then** recibe la respuesta estructurada con
   base `ok`.
2. **Given** una petición que llega al servidor con un encabezado `Host` que no es local ni
   `mcp.puropockets.space`, **When** el servidor la recibe, **Then** la rechaza.
3. **Given** una petición con un encabezado `Origin` que no está permitido, **When** el servidor la
   recibe, **Then** la rechaza.

---

### User Story 2 - El servicio vuelve solo tras un reinicio (Priority: P1)

El homelab se reinicia (corte de luz o reinicio manual). Sin intervención, la base, el servidor MCP
y el túnel vuelven a levantarse, y el conector de claude.ai sigue funcionando sin reconfigurarlo, con
la misma URL.

**Why this priority**: un servicio que no vuelve solo no sirve fuera de casa.

**Independent Test**: reiniciar el homelab y, sin tocar nada, llamar a `ping` desde Claude.

**Acceptance Scenarios**:

1. **Given** el homelab reiniciado, **When** termina de arrancar, **Then** los tres servicios están
   corriendo sin intervención y `ping` responde desde Claude por la misma URL.
2. **Given** un servicio que se cae por un error, **When** el proceso termina, **Then** Docker lo
   vuelve a levantar.

---

### User Story 3 - Saber si el túnel está sano y actualizar el despliegue (Priority: P2)

El propietario puede comprobar en pocos comandos que el túnel está conectado y que el servidor
responde, y puede traer cambios del repositorio y reiniciar el despliegue siguiendo un procedimiento
escrito.

**Why this priority**: operación básica necesaria desde este hito, porque el servidor ya vive fuera
del equipo de desarrollo.

**Independent Test**: siguiendo el README, el propietario ve el estado de salud del túnel y del
servidor, y aplica una actualización que termina con `ping` respondiendo.

**Acceptance Scenarios**:

1. **Given** el túnel conectado, **When** el propietario consulta el estado de los servicios,
   **Then** el túnel y el servidor aparecen como sanos.
2. **Given** el túnel sin credencial válida o desconectado, **When** consulta el estado, **Then** el
   túnel aparece como no sano.
3. **Given** cambios nuevos en el repositorio, **When** sigue el procedimiento de actualización,
   **Then** los servicios se reconstruyen, se aplican las migraciones y `ping` responde.

---

### User Story 4 - Pasos manuales guiados (Priority: P2)

El propietario sigue en orden, desde el README, los pasos que solo él puede hacer: Cloudflare,
Namecheap, homelab y claude.ai.

**Why this priority**: el hito depende de pasos fuera del repositorio; sin una guía clara, se pierden
registros DNS o se expone el token.

**Independent Test**: el README lista los pasos en orden, con lo que hay que copiar, dónde y cómo
comprobar cada uno, sin pedir nunca el token fuera del `.env` del homelab.

**Acceptance Scenarios**:

1. **Given** el README, **When** el propietario lo sigue, **Then** cada paso dice qué hacer, dónde y
   cómo saber que quedó bien.

---

### Edge Cases

- El token del túnel falta o es inválido: el túnel no queda sano y el estado lo muestra; el resto de
  los servicios sigue funcionando en local.
- El equipo de desarrollo no tiene token: `docker compose up` levanta solo la base y el servidor (el
  túnel no arranca).
- La base cae con el túnel arriba: `ping` desde Claude informa base `error` (comportamiento del
  Hito 1).
- Al cambiar los nameservers se pierden registros DNS existentes del dominio (por ejemplo, correo):
  el README pide revisarlos antes del cambio.
- DNSSEC activo en Namecheap al cambiar los nameservers: el dominio deja de resolver; el README pide
  desactivarlo antes.
- Alguien encuentra la URL pública: solo puede llamar a `ping`, que no expone datos (riesgo aceptado
  en `HITOS.md` hasta el Hito 3).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El servidor MCP MUST ser accesible desde internet en `https://mcp.puropockets.space/mcp`
  mediante un túnel de Cloudflare con nombre.
- **FR-002**: El túnel MUST correr como un servicio de Docker Compose y tomar su token de
  `CF_TUNNEL_TOKEN` en `.env`. `.env.example` MUST tener la variable vacía. El token MUST NOT
  aparecer en el repositorio, en la documentación ni en la salida de comandos que el proyecto pida
  ejecutar.
- **FR-003**: El túnel MUST arrancar solo donde se active de forma explícita (el homelab); en el
  equipo de desarrollo, `docker compose up` MUST levantar solo la base y el servidor.
- **FR-004**: El servidor MCP MUST NOT publicar puertos hacia el exterior: el túnel lo alcanza por la
  red interna de Docker, y para pruebas locales el puerto sigue publicado solo en `127.0.0.1`.
- **FR-005**: El servidor MUST aceptar el encabezado `Host` `mcp.puropockets.space` además de los
  hosts locales, y MUST rechazar cualquier otro.
- **FR-006**: El servidor MUST aceptar peticiones sin encabezado `Origin` y con `Origin` permitido
  (`https://mcp.puropockets.space`, los orígenes locales y los configurados), y MUST rechazar
  cualquier otro `Origin`.
- **FR-007**: El nombre público y los orígenes permitidos MUST ser configurables por variables de
  entorno, con `mcp.puropockets.space` como valor documentado.
- **FR-008**: Todos los servicios MUST reiniciarse solos tras un reinicio del homelab o una caída
  (`restart: unless-stopped`), siempre que Docker arranque con el sistema.
- **FR-009**: El túnel y el servidor MUST tener comprobaciones de salud que Docker muestre en el
  estado de los servicios.
- **FR-010**: El servidor MUST seguir exponiendo solo `ping`, sin datos ni autenticación (FR-017 del
  Hito 1 sigue vigente).
- **FR-011**: El README MUST incluir, en orden: alta del dominio en Cloudflare con revisión de los
  registros DNS, DNSSEC y cambio de nameservers en Namecheap, creación del túnel y del nombre público,
  instalación de Docker en el homelab, despliegue, conector en claude.ai, prueba con datos móviles,
  prueba de reinicio y medición de memoria en el homelab.
- **FR-012**: El README MUST documentar cómo actualizar el despliegue (traer cambios y reiniciar) y
  cómo comprobar que el túnel está sano.
- **FR-013**: `ping` MUST poder llamarse en el homelab sin instalar herramientas extra (desde el
  propio contenedor del servidor).
- **FR-014**: `docs/plan-tecnico.md` MUST registrar el dominio, el subdominio, la arquitectura del
  túnel, los hosts y orígenes permitidos y la versión fijada de `cloudflared`.

### Reglas citadas

- Gobernanza, regla no negociable 1: ningún dato financiero real antes del hito de autenticación
  (FR-010).
- Gobernanza, regla no negociable 4: el hito incluye sus pruebas automáticas.
- Principio 3.10: datos almacenados en el servidor del propietario; tránsito por Cloudflare y
  Anthropic aceptado; minimización (la respuesta de `ping` no cambia).

### Key Entities

Sin entidades nuevas. El estado de salud de `ping` es el del Hito 1.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Desde claude.ai, usando datos móviles, Claude llama a `ping` y obtiene base `ok`.
- **SC-002**: Tras reiniciar el homelab, el servicio vuelve solo y el conector funciona sin
  reconfigurarlo, en el 100 % de los reinicios probados.
- **SC-003**: La URL del conector no cambia entre reinicios ni actualizaciones.
- **SC-004**: El 100 % de las peticiones con `Host` u `Origin` no permitidos son rechazadas (prueba
  automática).
- **SC-005**: En el equipo de desarrollo, `docker compose up` no arranca el túnel ni falla por la
  falta de token.
- **SC-006**: El consumo de memoria del homelab con los tres servicios queda registrado en
  `docs/plan-tecnico.md`.

## Assumptions

- El homelab es un equipo Linux con acceso a internet y Docker Engine con el plugin de Compose.
- El propietario tiene acceso a las cuentas de Namecheap, Cloudflare (plan gratuito) y claude.ai.
- El túnel es "remotamente administrado" (se configura en el panel de Cloudflare y se identifica con
  un token), de modo que el repositorio no guarda credenciales ni archivos del túnel.
- Las pruebas que requieren cuentas, DNS o el homelab (SC-001, SC-002, SC-003, SC-006) las hace el
  propietario; las de encabezados y configuración se automatizan.
