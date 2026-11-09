# Research: Autenticación (003-autenticacion-oauth)

**Fecha:** 2026-11-09 · Revisión previa aprobada por el propietario.

## R1. Lo que aporta el SDK `mcp==2.3.0` (verificado en el código instalado)

- Rutas del servidor de autorización: `/authorize`, `/token`, `/register`, `/revoke` y
  `/.well-known/oauth-authorization-server` (RFC 8414); metadatos del recurso protegido en
  `/.well-known/oauth-protected-resource/mcp` (RFC 9728).
- PKCE: `/token` calcula SHA-256 del `code_verifier` y lo compara con el desafío; anuncia
  `code_challenge_methods_supported: ["S256"]`.
- `/authorize` valida la URL de retorno contra las registradas del cliente.
- `/register`: acepta `token_endpoint_auth_method: "none"` (cliente público, sin secreto); delega en
  `provider.register_client`, que puede rechazar con `RegistrationError`.
- Middleware Bearer: 401 con `WWW-Authenticate: Bearer error=…, resource_metadata="…"`; valida
  vencimiento y, con `validate_token_resource=True`, que el token sea del recurso configurado.
- `scopes_supported` del servidor de autorización sale de `valid_scopes`; el del recurso, de
  `required_scopes`.
- Se deja como está (decisión del propietario): la comparación de PKCE con `!=` y los metadatos que
  anuncian `client_secret_post`/`client_secret_basic`.

## R2. Requisitos de Claude (documentación oficial vigente)

- URL de retorno documentada: `https://claude.ai/api/mcp/auth_callback` (se permite también la de
  `claude.com` por decisión del propietario). Claude Code usa redirecciones locales: fuera.
- Claude usa CIMD solo si el servidor anuncia `client_id_metadata_document_supported` y `"none"`;
  como el SDK no los anuncia, usará DCR, registrándose como cliente público.
- 401 obligatorio con `resource_metadata`; el `resource` de los metadatos debe ser exactamente la URL
  del conector; solo se usa el primer `authorization_servers`.
- `offline_access`: Claude lo agrega si el servidor lo anuncia, para obtener refresco. Rotación de
  refresco obligatoria para clientes públicos, con `invalid_grant` cuando ya no vale.
- `/token` recibe `application/x-www-form-urlencoded` (el SDK lo soporta).
- Tiempos máximos: 10 s descubrimiento, registro y token; 30 s refresco.
- La configuración de autenticación de un conector no se puede cambiar: hay que quitar el conector
  del Hito 2 y agregarlo de nuevo.

## R3. Decisiones propias

- **Solo clientes públicos:** el SDK compara el secreto de clientes confidenciales en claro, lo que
  obligaría a guardarlo sin hash. Se rechazan en el registro.
- **Tokens opacos** de 256 bits (`secrets.token_urlsafe(32)`) con prefijo (`ppa_`, `ppr_`, `ppc_`);
  se guarda su SHA-256 (suficiente para valores aleatorios de alta entropía).
- **Cadenas (familias):** cada código de autorización inicia una cadena; cada refresco marca el
  token usado y emite un par nuevo en la misma cadena; reutilizar uno usado revoca la cadena.
- **Solicitudes de inicio de sesión pendientes** en memoria con vencimiento de 10 minutos (un
  reinicio obliga a reintentar; no hay datos de valor).
- **argon2-cffi 25.1.0** se instala con binarios en `python:3.14-slim` (sin gcc); parámetros por
  defecto: 0,15 s en el equipo de desarrollo. Los parámetros viajan dentro del hash: ajustarlos es
  generar el hash con otros valores (`scripts/hash_password.py`).
- **Healthcheck del contenedor:** pasa a consultar los metadatos públicos del recurso protegido, porque
  `ping` ya exige token.

## Fuentes

- https://claude.com/docs/connectors/building/authentication.md
- https://claude.com/docs/connectors/custom
- Código del SDK en `.venv/Lib/site-packages/mcp/server/auth/`.
