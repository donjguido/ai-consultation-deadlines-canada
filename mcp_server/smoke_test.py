"""In-process smoke test for the MCP server. No network, no API key.

    python -m mcp_server.smoke_test            # uses site/items.json
    python -m mcp_server.smoke_test path/to/items.json
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mcp import Client

from mcp_server import server


async def main(items_path: str) -> None:
    server.STORE.location = items_path
    server.STORE._items = []

    async with Client(server.mcp) as client:
        tools = await client.list_tools()
        names = sorted(t.name for t in tools.tools)
        print("tools:", ", ".join(names))
        assert {"list_open", "closing_soon", "search", "get_item", "list_topics", "monitor_status"} <= set(names)

        status = (await client.call_tool("monitor_status", {})).structured_content
        print("counts:", status["counts"], "| source:", status["data_source"])

        open_items = (await client.call_tool("list_open", {"limit": 5})).structured_content["result"]
        print(f"list_open -> {len(open_items)} shown; first:", open_items[0]["id"] if open_items else None)

        soon = (await client.call_tool("closing_soon", {"days": 30})).structured_content["result"]
        print(f"closing_soon(30) -> {len(soon)}")

        hits = (await client.call_tool("search", {"query": "privacy"})).structured_content["result"]
        print(f"search('privacy') -> {len(hits)}")

        if open_items:
            detail = (await client.call_tool("get_item", {"id": open_items[0]["id"], "lang": "fr"})).structured_content
            print("get_item(fr) title:", detail["title"])

        bad = await client.call_tool("get_item", {"id": "does-not-exist"})
        assert bad.is_error, "missing id should be an error"

        topics = (await client.call_tool("list_topics", {})).structured_content["result"]
        print("topics:", ", ".join(f"{t['topic']}({t['open_items']})" for t in topics[:6]), "...")

        res = await client.list_resources()
        print("resources:", ", ".join(str(r.uri) for r in res.resources))
        body = await client.read_resource("monitor://items")
        print("monitor://items bytes:", len(getattr(body.contents[0], "text", "")))

    print("OK")


if __name__ == "__main__":
    default = Path(__file__).resolve().parent.parent / "site" / "items.json"
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else str(default)))
