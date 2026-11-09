# Feature Specification: Autenticación (OAuth con servidor propio)

**Feature Branch**: `hito-3-autenticacion`

**Created**: 2026-11-09

**Status**: Draft

**Input**: User description (prompt del Hito 3 en `HITOS.md`): "El propietario necesita que solo él pueda invocar las tools del servidor MCP. Al agregar el conector en Claude debe aparecer un inicio de sesión; sin sesión válida, las llamadas deben rechazarse. Debe poder desconectar y reconectar el conector, y revocar el acceso si lo necesita. Incluye pruebas automáticas que verifiquen los criterios de aceptación."

**Hito**: 3 (Autenticación), según `HITOS.md`.

## Clarifications

### Session 2026-11-09

Decisiones del propietario tras la revisión previa (documentación de Anthropic y SDK `mcp==2.3.0`):

- Q: ¿Servidor de autorización propio o externo? → A: Propio y mínimo, OAuth 2.1 para un único usuario, construido sobre el módulo de autenticación del SDK (sin criptografía propia).
- Q: ¿Qué URL de retorno se aceptan? → A: `https://claude.ai/api/mcp/auth_callback` y `https://claude.com/api/mcp/auth_callback`, en una lista blanca configurable. Se registra cuál se usó y se muestra el dominio de retorno en el inicio de sesión. Claude Code (redirecciones locales) queda fuera.
- Q: ¿Cómo se registra el cliente? → A: Registro dinámico (RFC 7591) cerrado por defecto; solo se activa con `OAUTH_REGISTRATION_ENABLED=true` mientras se agrega el conector. Máximo 10 clientes y límite de intentos. Se documenta la alternativa "cliente propio".
- Q: ¿Duraciones? → A: Configurables. Acceso 1 hora; refresco 30 días con rotación y revocación de toda la cadena si se reutiliza uno viejo; código de autorización 5 minutos, de un solo uso. Modo de duraciones cortas para pruebas (acceso de 2 minutos), desactivado por defecto. Se anuncia `offline_access`; los tokens se ligan al recurso `https://mcp.puropockets.space/mcp`.
- Q: ¿Contraseña? → A: Hash argon2 (argon2-cffi) en `.env`, entre comillas simples; parámetros que den menos de 1 segundo en el homelab. La contraseña en texto plano nunca se guarda ni se imprime.
- Q: ¿Límite de intentos? → A: Por IP (encabezado `CF-Connecting-IP`) con un bloqueo global corto, solo para el inicio de sesión; nunca afecta a `/mcp` con token válido.
- Q: ¿Almacenamiento? → A: Tablas de autenticación (nombres en inglés) en la migración `0002`, guardando solo hashes de códigos y tokens.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Solo el propietario usa el MCP (Priority: P1)

Sin un token válido, el servidor rechaza cualquier llamada a `/mcp` con 401 e indica dónde
autenticarse. Con un token válido, emitido tras iniciar sesión con la contraseña del propietario,
`ping` funciona.

**Independent Test**: un cliente de prueba recorre registro → autorización con PKCE → inicio de
sesión → token, y llama a `/mcp` con y sin token.

**Acceptance Scenarios**:

1. **Given** una petición a `/mcp` sin token, **Then** 401 con `WWW-Authenticate` que incluye
   `resource_metadata`.
2. **Given** un token inválido, vencido o revocado, **Then** 401.
3. **Given** el flujo completo con la contraseña correcta, **Then** el token permite llamar a `ping`.
4. **Given** una contraseña incorrecta, **Then** no se emite código y, tras varios intentos, se
   bloquea temporalmente el inicio de sesión desde esa IP (y globalmente si los fallos siguen).

---

### User Story 2 - Conectar el conector de claude.ai (Priority: P1)

Al agregar el conector, Claude descubre el servidor de autorización, se registra (mientras el
registro está abierto), abre la página de inicio de sesión que muestra a qué dominio volverá
("claude.ai" o "claude.com"), y tras iniciar sesión el conector funciona.

**Acceptance Scenarios**:

1. **Given** el registro abierto y una URL de retorno permitida, **Then** el registro se acepta.
2. **Given** una URL de retorno no permitida, **Then** el registro se rechaza.
3. **Given** el registro cerrado, **Then** el endpoint de registro no está disponible.
4. **Given** 10 clientes registrados, **Then** el siguiente registro se rechaza.

---

### User Story 3 - Sesiones que duran y se pueden cortar (Priority: P2)

El conector sigue funcionando más allá de la hora del token de acceso gracias al refresco. El
propietario puede desconectar y reconectar el conector, y revocar todo el acceso.

**Acceptance Scenarios**:

1. **Given** un token de refresco válido, **Then** se emite un par nuevo y el anterior deja de valer.
2. **Given** un token de refresco ya usado, **Then** se rechaza (`invalid_grant`) y se revoca toda la
   cadena (los tokens emitidos después también dejan de valer).
3. **Given** una revocación (endpoint de revocación o comando del propietario), **Then** los tokens
   afectados reciben 401.
4. **Given** un código de autorización ya usado o vencido, **Then** se rechaza.

### Edge Cases

- `OWNER_PASSWORD_HASH` vacío o inválido: el servidor arranca, `/mcp` exige token y el inicio de
  sesión queda deshabilitado con un mensaje claro (nadie puede obtener tokens).
- Cliente que pide un recurso distinto de `https://mcp.puropockets.space/mcp`: se rechaza.
- Cliente confidencial (con secreto): se rechaza; solo se aceptan clientes públicos, para no guardar
  secretos en claro.
- Reinicio del servidor durante un inicio de sesión: la solicitud pendiente se pierde y hay que
  reintentar desde Claude; los tokens emitidos siguen valiendo (están en la base).
- La comprobación de salud del contenedor ya no puede usar `ping` sin token.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `/mcp` MUST exigir un token Bearer válido; sin él, MUST responder 401 con
  `WWW-Authenticate` y `resource_metadata`.
- **FR-002**: El servidor MUST publicar los metadatos del recurso protegido (RFC 9728) con
  `resource = https://mcp.puropockets.space/mcp` y los del servidor de autorización (RFC 8414), con
  `S256` y `offline_access`.
- **FR-003**: La autorización MUST usar código de autorización con PKCE S256.
- **FR-004**: El registro dinámico (RFC 7591) MUST estar cerrado salvo con
  `OAUTH_REGISTRATION_ENABLED=true`; MUST aceptar solo clientes públicos, solo URL de retorno de la
  lista blanca (`OAUTH_ALLOWED_REDIRECT_URIS`), como máximo `OAUTH_MAX_CLIENTS` (10) clientes, y con
  límite de intentos.
- **FR-005**: El inicio de sesión MUST verificar la contraseña del propietario contra
  `OWNER_PASSWORD_HASH` (argon2), MUST mostrar el dominio de retorno, y MUST limitar los intentos por
  IP (`CF-Connecting-IP`) con un bloqueo global corto.
- **FR-006**: Los tokens de acceso MUST durar `OAUTH_ACCESS_TOKEN_TTL_SECONDS` (3600); los de
  refresco `OAUTH_REFRESH_TOKEN_TTL_SECONDS` (2592000) con rotación; los códigos
  `OAUTH_AUTH_CODE_TTL_SECONDS` (300), de un solo uso. `OAUTH_SHORT_LIFETIMES=true` activa duraciones
  cortas para pruebas.
- **FR-007**: Reutilizar un token de refresco ya rotado MUST revocar toda su cadena.
- **FR-008**: Solo se MUST guardar el hash (SHA-256) de códigos y tokens.
- **FR-009**: Los tokens MUST ligarse al recurso, y el servidor MUST rechazar tokens de otro recurso
  (`validate_token_resource`).
- **FR-010**: MUST existir revocación por el endpoint estándar (RFC 7009) y un comando del
  propietario que revoque todo.
- **FR-011**: Los registros MUST NOT contener contraseñas, hashes, códigos ni tokens; MUST registrar
  la URL de retorno usada (dominio) y los eventos de registro, inicio de sesión, refresco, reutilización
  y revocación.
- **FR-012**: `scripts/hash_password.py` MUST pedir la contraseña con `getpass`, imprimir solo el hash
  y permitir medir el tiempo de verificación.
- **FR-013**: `docs/plan-tecnico.md` MUST registrar la decisión del servidor de autorización, y la
  sección 3 de `HITOS.md` MUST dejar de listarla como pendiente.

### Reglas citadas

- Gobernanza, regla no negociable 1: a partir de este hito se permite guardar datos reales.
- Gobernanza, regla no negociable 4: pruebas automáticas del hito.
- Principio 3.10: minimización (los registros no contienen secretos).

### Key Entities

- **Cliente OAuth**: identificador, metadatos registrados (nombre, URL de retorno), fecha.
- **Código de autorización**: hash, cliente, URL de retorno, desafío PKCE, scopes, recurso,
  vencimiento, uso.
- **Token de acceso / de refresco**: hash, cliente, scopes, recurso, cadena (familia), vencimiento,
  revocación; el de refresco además registra cuándo se usó.

## Success Criteria *(mandatory)*

- **SC-001**: Una llamada a `/mcp` sin token recibe 401 (prueba automática).
- **SC-002**: Agregar el conector en claude.ai, iniciar sesión y llamar a `ping` funciona.
- **SC-003**: Desconectar y reconectar el conector funciona.
- **SC-004**: Un token inválido o vencido es rechazado (prueba automática).
- **SC-005**: Flujo completo, URL de retorno no permitida, refresco, reutilización y revocación
  cubiertos por pruebas automáticas.
- **SC-006**: El inicio de sesión tarda menos de 1 segundo en el homelab.

## Assumptions

- Claude usará DCR (el servidor no anuncia CIMD) y se registrará como cliente público.
- El túnel y el despliegue del Hito 2 están operativos para las pruebas con claude.ai (SC-002, SC-003,
  SC-006, a cargo del propietario).
