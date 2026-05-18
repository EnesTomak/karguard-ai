"""MCP client gateway package."""

from .schemas import MCPToolCallRequest, MCPToolCallResult, MCPToolTrace

__all__ = [
    "MCPClientGateway",
    "MCPToolCallRequest",
    "MCPToolCallResult",
    "MCPToolTrace",
    "mcp_gateway",
]


def __getattr__(name: str):
    if name in {"MCPClientGateway", "mcp_gateway"}:
        from .gateway import MCPClientGateway, mcp_gateway

        return {"MCPClientGateway": MCPClientGateway, "mcp_gateway": mcp_gateway}[name]
    raise AttributeError(name)
