"""In-process MCP server check against a built items.json. Mirrors
mcp_server/smoke_test.py but runs on the fixed sample store, offline."""
import asyncio

import pytest

mcp = pytest.importorskip("mcp")

from mcp import Client  # noqa: E402

from mcp_server import server  # noqa: E402
from pipeline import build  # noqa: E402
from tests.conftest import TODAY  # noqa: E402

TOOLS = {"list_open", "closing_soon", "search", "get_item", "list_topics", "monitor_status"}


@pytest.fixture
def site_items(tmp_path, sample_items):
    out = tmp_path / "site"
    out.mkdir()
    build.build_site(sample_items, out, TODAY)
    return out / "items.json"


def _run(coro):
    return asyncio.run(coro)


def test_server_serves_the_store(site_items):
    server.STORE.location = str(site_items)
    server.STORE._items = []

    async def go():
        async with Client(server.mcp) as client:
            names = {t.name for t in (await client.list_tools()).tools}
            assert TOOLS <= names

            status = (await client.call_tool("monitor_status", {})).structured_content
            # The server judges status by the real calendar, so only date-independent
            # facts are asserted: the flagged item is retired, the far-future one is open.
            assert status["counts"]["retired"] >= 1
            assert status["counts"]["open"] >= 1

            open_items = (await client.call_tool("list_open", {"limit": 50})).structured_content["result"]
            ids = {r["id"] for r in open_items}
            assert "retired-flag" not in ids
            assert "no-deadline" in ids

            hits = (await client.call_tool("search", {"query": "consultation"})).structured_content["result"]
            assert hits

            detail = (await client.call_tool("get_item", {"id": "brand-new", "lang": "fr"})).structured_content
            assert detail["title"] == "Consultation de test"
            fallback = (await client.call_tool("get_item", {"id": "untranslated", "lang": "fr"})).structured_content
            assert fallback["title"].startswith("Test consultation")

            bad = await client.call_tool("get_item", {"id": "does-not-exist"})
            assert bad.is_error

            topics = (await client.call_tool("list_topics", {})).structured_content["result"]
            assert {t["topic"] for t in topics} >= {"privacy", "standards"}

            res = await client.list_resources()
            assert any(str(r.uri) == "monitor://items" for r in res.resources)

    _run(go())
