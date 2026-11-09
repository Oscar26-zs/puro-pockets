"""Prueba de humo del SDK de MCP (FR-018).

Si esta prueba falla tras actualizar el SDK, la ruta de importación o la versión cambiaron:
seguir el procedimiento "Actualizar el SDK de MCP" de docs/plan-tecnico.md.
"""

import importlib.metadata


def test_mcpserver_se_importa_desde_la_ruta_fijada():
    from mcp.server.mcpserver import MCPServer

    assert MCPServer.__name__ == "MCPServer"


def test_version_del_sdk_fijada():
    assert importlib.metadata.version("mcp") == "2.3.0"
