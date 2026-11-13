// Comprueba que la compilación de producción no incluye datos de ejemplo ni referencias a otros orígenes (CDN, fuentes, analíticas). Corre después de `vite build`.
import { readdirSync, readFileSync, statSync } from "node:fs"
import { join } from "node:path"

const dist = new URL("../dist/", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1")
const files = []
const walk = (dir) => {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) walk(path)
    else if (/\.(js|css|html)$/.test(name)) files.push(path)
  }
}
walk(dist)

const forbidden = [
  "Suscripción de video", // marcador de los fixtures
  "Salida con amigos",
  "Fondo de emergencia",
  "fonts.googleapis.com",
  "fonts.gstatic.com",
  "googletagmanager",
  "google-analytics",
  "cdn.jsdelivr.net",
  "unpkg.com",
]
const problems = []
for (const file of files) {
  const text = readFileSync(file, "utf8")
  for (const needle of forbidden) {
    if (text.includes(needle)) problems.push(`${file}: contiene «${needle}»`)
  }
  for (const match of text.matchAll(/(?:src|href)=["'](https?:)?\/\/[^"']+/g)) {
    problems.push(`${file}: recurso de otro origen ${match[0]}`)
  }
}
if (files.length === 0) problems.push("dist/ está vacío: corre vite build primero")
if (problems.length) {
  console.error(problems.join("\n"))
  process.exit(1)
}
console.log(`check-bundle: ${files.length} archivos sin datos de ejemplo ni otros orígenes`)
