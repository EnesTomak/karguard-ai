"""Process manager placeholder for external MCP server transports."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MCPServerProcessSpec:
    server: str
    command: list[str]


class MCPProcessManager:
    """Tracks planned lifecycle hooks for stdio-based MCP server processes."""

    def __init__(self) -> None:
        self._started_servers: set[str] = set()

    def start_server(self, spec: MCPServerProcessSpec) -> None:
        """Mark server as started (stdio startup wiring is planned)."""
        self._started_servers.add(spec.server)

    def stop_server(self, server: str) -> None:
        """Mark server as stopped."""
        self._started_servers.discard(server)

    def is_running(self, server: str) -> bool:
        return server in self._started_servers
