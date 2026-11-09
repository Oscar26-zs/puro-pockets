# Puro Pockets

Aplicación personal de finanzas que se usa conversando con Claude a través de un servidor MCP.
Este repositorio está en el **Hito 2 (Acceso remoto sin datos)**: el servidor MCP y la base de datos
se levantan con un solo comando, una tool `ping` informa si ambos están operativos, y en el homelab
un túnel de Cloudflare publica el servidor en `https://mcp.puropockets.space/mcp` para usarlo desde
claude.ai. Todavía no hay datos financieros ni autenticación (ver [HITOS.md](HITOS.md)).

- Desarrollo en tu equipo: secciones 1 a 5.
- Despliegue en el homelab y conector de Claude: sección
  [Despliegue en el homelab](#despliegue-en-el-homelab-hito-2).

Documentos del proyecto: [constitución](.specify/memory/constitution.md) (reglas),
[plan técnico](docs/plan-tecnico.md) (técnica) y [HITOS.md](HITOS.md) (hoja de ruta).

## Requisitos

- [Docker Desktop](https://docs.docker.com/desktop/) con Docker Compose (en Windows, con WSL 2).
- [uv](https://docs.astral.sh/uv/) (gestor de Python; instala la versión de Python que haga falta).
- Puertos `5432` y `8000` libres en `127.0.0.1`.

## 1. Configurar

```powershell
git clone <url-del-repositorio> puro-pockets
cd puro-pockets
copy .env.example .env        # en Linux o macOS: cp .env.example .env
```

Edita `.env` y cambia `cambia-esta-contrasena` por una contraseña propia, **en las dos líneas** donde
aparece (`POSTGRES_PASSWORD` y `DATABASE_URL`). Usa solo letras, números, `-` y `_`: otros caracteres
(como `@`, `:` o `/`) rompen la URL de conexión. `.env` nunca se sube al repositorio.

## 2. Levantar los servicios

```powershell
docker compose up -d --build
docker compose ps
```

Debe mostrar `db` como `healthy` y `mcp` como `running`, con los puertos publicados solo en
`127.0.0.1` (`127.0.0.1:5432` y `127.0.0.1:8000`).

## 3. Aplicar las migraciones

```powershell
docker compose exec mcp alembic upgrade head
```

Para revertir hasta el inicio y volver a aplicar:

```powershell
docker compose exec mcp alembic downgrade base
docker compose exec mcp alembic upgrade head
```

## 4. Comprobar que está vivo (`ping`)

```powershell
uv run python scripts/ping.py
```

Respuesta esperada:

```json
{"server": "ok", "database": "ok", "detail": null}
```

Si la base no responde, `ping` contesta igual, en menos de 5 segundos, con `"database": "error"` y un
motivo breve en `detail`. El servidor MCP escucha en `http://127.0.0.1:8000/mcp` (transporte
Streamable HTTP); cualquier cliente MCP local, como el MCP Inspector, puede conectarse a esa URL.

## 5. Pruebas y estilo

La primera vez, `uv sync` instala las dependencias exactas de `uv.lock`.

```powershell
uv sync
uv run pytest -m "not integration"   # pruebas unitarias (lo mismo que corre en GitHub)
uv run pytest                        # unitarias + integración (requiere los servicios levantados)
uv run ruff check .
uv run ruff format --check .
```

En cada push, GitHub Actions corre `ruff` y las pruebas unitarias
([.github/workflows/ci.yml](.github/workflows/ci.yml)).

## Detener y borrar datos

```powershell
docker compose down        # detiene; los datos se conservan en el volumen pgdata
docker compose down -v     # detiene y BORRA los datos de la base (irreversible)
```

## Despliegue en el homelab (Hito 2)

Arquitectura: `Claude → https://mcp.puropockets.space → Cloudflare → túnel (contenedor cloudflared en
el homelab) → http://mcp:8000 (red interna de Docker) → servidor MCP → base de datos`. El homelab no
abre puertos hacia internet: el túnel sale hacia Cloudflare. Los puertos del servidor y de la base solo
se publican en `127.0.0.1` del propio homelab.

> **Token del túnel:** solo existe en el `.env` del homelab. Nunca lo pegues en el repositorio, en un
> chat (incluido Claude), en issues ni en capturas. No ejecutes `docker compose config` sin opciones en
> el homelab: imprime las variables del `.env`, incluido el token. Si se filtra, rótalo en Cloudflare
> (ver "Si el token se filtra").

> **Riesgo aceptado en este hito:** la URL es pública y no tiene autenticación; solo expone `ping`, que
> no contiene datos. Si prefieres, apaga el túnel entre pruebas con `docker compose stop cloudflared`.
> La autenticación llega en el Hito 3.

Haz los pasos en orden. Cada uno dice cómo comprobar que quedó bien.

### Paso 1. Agregar el dominio a Cloudflare

1. Crea una cuenta en [Cloudflare](https://dash.cloudflare.com/) (plan gratuito).
2. **Add a domain** → `puropockets.space` → plan **Free**.
3. Cloudflare importa los registros DNS que encuentre. **Compáralos con los de Namecheap**
   (Namecheap → Domain List → Manage → Advanced DNS) y agrega a mano en Cloudflare los que falten,
   sobre todo correo (`MX`, `TXT` de SPF/DKIM/DMARC) y verificaciones de otros servicios.
4. Anota los **dos nameservers** que te asigna Cloudflare (algo como `xxx.ns.cloudflare.com`).

**Comprobación:** los registros DNS en Cloudflare coinciden con los de Namecheap.

### Paso 2. DNSSEC y nameservers en Namecheap

1. En Namecheap → Domain List → Manage → **Advanced DNS**: si **DNSSEC** está activado,
   **desactívalo antes** de cambiar los nameservers (si no, el dominio deja de resolver).
2. En **Domain** → **Nameservers** → **Custom DNS** → pega los dos nameservers de Cloudflare → guarda.
3. Espera a que Cloudflare marque el dominio como **Active** (de minutos a 24 horas; te avisa por
   correo).
4. Opcional, después de que esté activo: activa DNSSEC en Cloudflare (DNS → Settings) y copia el
   registro **DS** que te muestra en Namecheap (Advanced DNS → DNSSEC).

**Comprobación:** el dominio aparece como **Active** en Cloudflare.

### Paso 3. Crear el túnel y el nombre público

1. En Cloudflare → **Zero Trust** → **Networks** → **Tunnels** → **Create a tunnel** →
   **Cloudflared** → nombre `puro-pockets`.
2. En la pantalla de instalación, elige **Docker**. Verás un comando con `--token eyJ...`: **no lo
   ejecutes**. Copia solo el valor del token; lo pegarás en el paso 5, en el `.env` del homelab.
3. **Public hostname** (o "Route traffic"):
   - Subdomain: `mcp` · Domain: `puropockets.space` · Path: vacío.
   - Service: **HTTP** · URL: `mcp:8000`.
   - No cambies **HTTP Host Header** en las opciones avanzadas: el servidor solo acepta el `Host`
     `mcp.puropockets.space`, que el túnel reenvía tal cual.
4. Guarda. El túnel aparecerá como **Inactive** o **Down** hasta que arranque en el homelab.

**Comprobación:** en Cloudflare → DNS existe un registro `mcp` de tipo `CNAME` hacia
`<id>.cfargotunnel.com`, creado por el túnel.

### Paso 4. Docker en el homelab

1. Instala Docker Engine con el plugin de Compose siguiendo la
   [guía oficial para tu distribución](https://docs.docker.com/engine/install/).
2. Haz que Docker arranque con el sistema (necesario para que todo vuelva solo tras un reinicio):

   ```bash
   sudo systemctl enable --now docker
   ```

3. Opcional: usa Docker sin `sudo` con `sudo usermod -aG docker $USER` (cierra la sesión y vuelve a
   entrar).

**Comprobación:** `docker --version` y `docker compose version` responden, y
`systemctl is-enabled docker` dice `enabled`.

### Paso 5. Desplegar en el homelab

```bash
git clone <url-del-repositorio> puro-pockets
cd puro-pockets
git switch <rama-o-etiqueta-a-desplegar>    # por ejemplo, la etiqueta del Hito 2
cp .env.example .env
nano .env                                   # o el editor que prefieras
```

En el `.env` del homelab:

- Cambia `cambia-esta-contrasena` por una contraseña propia en `POSTGRES_PASSWORD` y en
  `DATABASE_URL` (solo letras, números, `-` y `_`).
- `CF_TUNNEL_TOKEN=` → pega el token del paso 3 (sin comillas ni espacios).
- `COMPOSE_PROFILES=tunnel` (esto activa el contenedor del túnel).
- Deja `MCP_PUBLIC_HOSTNAME=mcp.puropockets.space`.

Protege el archivo y levanta todo:

```bash
chmod 600 .env
docker compose up -d --build
docker compose exec mcp alembic upgrade head
docker compose ps
```

**Comprobación:** `docker compose ps` muestra `db`, `mcp` y `cloudflared` como **healthy** (el túnel
puede tardar hasta un minuto). En Cloudflare, el túnel pasa a **Healthy**.

### Paso 6. Probar `ping` en el homelab y desde fuera

En el homelab (no necesita uv; usa el cliente que viene en la imagen):

```bash
docker compose exec mcp python scripts/ping.py
```

Desde tu equipo de desarrollo (cualquier red):

```powershell
uv run python scripts/ping.py --url https://mcp.puropockets.space/mcp
```

**Comprobación:** ambos responden `{"server": "ok", "database": "ok", "detail": null}`.

### Paso 7. Conector en claude.ai

1. En claude.ai → **Customize** → **Connectors** → **Add custom connector**.
2. Nombre: `Puro Pockets` · URL: `https://mcp.puropockets.space/mcp`.
3. Autenticación: **No sign-in** (sin inicio de sesión; la autenticación llega en el Hito 3).
4. Guarda y activa el conector en una conversación.

**Comprobación:** en una conversación nueva, pide "Llama a la tool ping de Puro Pockets" y Claude
muestra el resultado con `database: ok`.

### Paso 8. Prueba con datos móviles (criterio del hito)

Desde el celular, **con el wifi apagado**, abre Claude, usa el conector y pide que llame a `ping`.

**Comprobación:** responde con `database: ok`.

### Paso 9. Prueba de reinicio (criterio del hito)

```bash
sudo reboot
```

Cuando el homelab vuelva, sin tocar nada: `docker compose ps` debe mostrar los tres servicios
**healthy**, y Claude debe poder llamar a `ping` **sin reconfigurar el conector** y con la misma URL.

### Paso 10. Medir la memoria en el homelab

Con todo levantado y estabilizado (unos minutos después de arrancar):

```bash
docker stats --no-stream
for i in $(seq 1 20); do docker compose exec -T mcp python scripts/ping.py > /dev/null; done
docker stats --no-stream
```

Anota los valores de `db`, `mcp` y `cloudflared` (en reposo y tras 20 `ping`) en la tabla "Medición de
memoria" de [docs/plan-tecnico.md](docs/plan-tecnico.md), con la fecha y el equipo.

### Comprobar que el túnel está sano

| Qué mirar | Comando o lugar | Sano |
|---|---|---|
| Estado de los servicios | `docker compose ps` | `cloudflared` y `mcp` **healthy** |
| Salud del túnel (detalle) | `docker inspect --format '{{json .State.Health.Status}}' puro-pockets-cloudflared-1` | `"healthy"` |
| Conexiones del túnel | `docker compose logs --tail 30 cloudflared` | líneas `Registered tunnel connection` |
| Panel de Cloudflare | Zero Trust → Networks → Tunnels | **Healthy** |
| De punta a punta | `uv run python scripts/ping.py --url https://mcp.puropockets.space/mcp` | `database: ok` |

Si `cloudflared` no queda sano:

- Logs con `requires the ID or name of the tunnel`: falta `CF_TUNNEL_TOKEN` en el `.env`.
- Logs con errores de autenticación o `Unauthorized`: el token es inválido o fue rotado.
- `cloudflared` no aparece en `docker compose ps`: falta `COMPOSE_PROFILES=tunnel` en el `.env`.
- Desde fuera responde `Invalid Host header` (421): revisa que el nombre público sea
  `mcp.puropockets.space` y que no se haya configurado **HTTP Host Header** en Cloudflare.

### Actualizar el despliegue

```bash
cd puro-pockets
git fetch
git switch <rama-o-etiqueta-nueva>      # o: git pull, si sigues una rama
docker compose up -d --build            # reconstruye mcp y recrea lo que cambió
docker compose exec mcp alembic upgrade head
docker compose ps                       # todo healthy
docker compose exec mcp python scripts/ping.py
```

Si cambió `.env.example`, compáralo con tu `.env` (`diff .env.example .env`; ojo: muestra tu token en
pantalla, hazlo en privado) y agrega las variables nuevas. La URL del conector no cambia.

### Si el token se filtra

1. Cloudflare → Zero Trust → Networks → Tunnels → `puro-pockets` → **Refresh token** (o elimina el
   túnel y crea otro con el mismo nombre público).
2. Pon el token nuevo en el `.env` del homelab y ejecuta `docker compose up -d cloudflared`.

## Estructura

```text
src/puro_pockets/
├── config.py      # configuración desde variables de entorno
├── domain/        # reglas puras (sin MCP ni base de datos)
├── services/      # casos de uso
├── db/            # conexión a la base (SQLAlchemy + psycopg 3)
└── mcp/           # servidor MCP y tools
migrations/        # Alembic
tests/unit/        # pruebas unitarias
tests/integration/ # pruebas con los servicios levantados
scripts/ping.py    # cliente de prueba
```

## Actualizar el SDK de MCP

La versión del SDK está fijada (`mcp==2.3.0`). Actualizarla es una decisión deliberada: sigue el
procedimiento "Actualizar el SDK de MCP" de [docs/plan-tecnico.md](docs/plan-tecnico.md).

## Problemas frecuentes

- **El puerto 5432 u 8000 ya está en uso:** `docker compose up` falla con un mensaje de puerto
  ocupado. Cierra el programa que lo usa o cambia `POSTGRES_PORT` / `MCP_PORT` en `.env` (y el puerto
  de `DATABASE_URL`).
- **Falta una variable en `.env`:** Docker Compose indica cuál (por ejemplo, `Falta POSTGRES_PASSWORD
  en .env`).
- **Conexiones lentas desde el equipo:** usa `127.0.0.1` y no `localhost` en `DATABASE_URL`.
- **`ping` responde `database: error` después de cambiar la contraseña en `.env`:** Postgres solo
  aplica `POSTGRES_PASSWORD` la primera vez, cuando el volumen está vacío. Si cambias la contraseña
  después, la base conserva la anterior. En desarrollo, sin datos que conservar, borra el volumen y
  vuelve a levantar: `docker compose down -v` y `docker compose up -d --build` (luego aplica las
  migraciones). El volumen se llama `puro-pockets_pgdata` y lo comparten todas las copias del
  repositorio en el mismo equipo.
