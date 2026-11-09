# Contrato: tool MCP `ping`

**Hito:** 1 · **Spec:** FR-006, FR-007, FR-008 · **Transporte:** Streamable HTTP en
`http://127.0.0.1:8000/mcp` (puerto configurable con `MCP_PORT`)

## Entrada

Sin parámetros.

## Salida (contenido estructurado)

| Campo | Tipo | Valores | Cuándo |
|---|---|---|---|
| `server` | texto | `ok` | Siempre. Si el servidor responde, está operativo. |
| `database` | texto | `ok`, `error` | Siempre. |
| `detail` | texto o nulo | Mensaje breve en español | Solo cuando `database` es `error`; nulo en otro caso. |

La tool publica su esquema de salida (`outputSchema`), y el cliente recibe estos campos en el
contenido estructurado de la respuesta.

### Ejemplos

Base operativa:

```json
{ "server": "ok", "database": "ok", "detail": null }
```

Base caída o inalcanzable:

```json
{ "server": "ok", "database": "error", "detail": "La base de datos no respondió en 2 segundos." }
```

## Reglas

1. La base se comprueba con una consulta trivial y un tiempo límite de conexión de 2 segundos.
2. Una falla de la base **no** es un error de la tool: la respuesta es normal, con `database: "error"`.
3. `detail` nunca incluye credenciales, cadenas de conexión, nombres de host internos ni trazas
   (principio 3.10, minimización).
4. Tiempo de respuesta: menos de 2 segundos con la base operativa y menos de 5 segundos con la base
   caída (SC-004).
5. Si la base vuelve a estar disponible, la siguiente llamada informa `database: "ok"` sin reiniciar
   el servidor.

## Pruebas que verifican este contrato

- Unitaria (en memoria, `Client(mcp)`): con la comprobación de base simulada en `ok` y en `error`,
  la salida tiene exactamente los campos y valores de esta tabla.
- Integración (HTTP, servicios levantados): `database: "ok"`.
- Integración (URL de base inalcanzable): `database: "error"`, `detail` en español sin datos
  internos, respuesta en menos de 5 segundos.
