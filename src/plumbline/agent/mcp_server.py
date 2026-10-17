"""MCP server exposing Plumbline's tools.

Run standalone for any MCP client:  python -m plumbline.agent.mcp_server
The in-app agent connects to this same server in memory, so what the agent can do is exactly what the server offers.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from plumbline.agent.tools import READ_TOOLS, WORK_TOOLS

INSTRUCTIONS = (
    "Plumbline answers whether services are exposed to a software supply-chain incident. Verdicts are EXPOSED, "
    "CLEARED or UNKNOWN and come from deterministic code; quote them, never infer them. Most tools are read-only; "
    "hand_off_fix, claim_task and complete_task write only to the shared work queue that agents use to pass fixes to "
    "each other, and never change a verdict or a decision. Times are UTC ISO 8601. Cite the dependency path and receipt hash for EXPOSED results, and say what evidence is "
    "missing for UNKNOWN results."
)


def build_server() -> MCPServer:
    server = MCPServer("plumbline", instructions=INSTRUCTIONS)
    read_only = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)
    queue_write = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)
    for name, fn in READ_TOOLS.items():
        server.add_tool(fn, name=name, annotations=read_only)
    for name, fn in WORK_TOOLS.items():
        server.add_tool(fn, name=name, annotations=read_only if name == "list_tasks" else queue_write)
    return server


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
