from __future__ import annotations

import ast
from pathlib import Path


def _contains_banned_finance_mcp_import(source: str) -> bool:
    tree = ast.parse(source)
    banned_module = "app.mcp_servers.finance_mcp_server"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == banned_module:
                    return True

        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == banned_module:
                return True

            # Covers: from app.mcp_servers import finance_mcp_server
            if module.endswith("mcp_servers"):
                if any(alias.name == "finance_mcp_server" for alias in node.names):
                    return True

    return False


def test_no_service_direct_imports_finance_mcp_server():
    services_dir = Path(__file__).resolve().parents[1] / "app" / "services"
    offenders: list[str] = []

    for file_path in services_dir.rglob("*.py"):
        source = file_path.read_text(encoding="utf-8")
        if _contains_banned_finance_mcp_import(source):
            offenders.append(str(file_path.relative_to(services_dir.parent)))

    assert not offenders, (
        "services katmaninda direct finance_mcp_server import yasak. "
        f"Bulunan dosyalar: {offenders}"
    )
