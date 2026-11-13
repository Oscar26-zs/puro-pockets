import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import { PuroDashboard } from "@/components/puro-dashboard"
import "@/styles/globals.css"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <PuroDashboard />
  </StrictMode>,
)
