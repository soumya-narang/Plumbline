"""MCP server exposing Plumbline's tools.

Run standalone for any MCP client:  python -m plumbline.agent.mcp_server
The in-app agent connects to this same server in memory, so what the agent can do is exactly what the server offers.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from plumbline.agent.tools import TOOLS

INSTRUCTIONS = (
    "Plumbline answers whether services are exposed to a software supply-chain incident. Verdicts are EXPOSED, "
    "CLEARED or UNKNOWN and come from deterministic code; quote them, never infer them. All tools are read-only. "
    "Times are UTC ISO 8601. Cite the dependency path and receipt hash for EXPOSED results, and say what evidence is "
    "missing for UNKNOWN results."
)


def build_server() -> MCPServer:
    server = MCPServer("plumbline", instructions=INSTRUCTIONS)
    read_only = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)
    for name, fn in TOOLS.items():
        server.add_tool(fn, name=name, annotations=read_only)
    return server


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
