# MCP server

A read-only [Model Context Protocol](https://modelcontextprotocol.io) server that lets AI assistants (Claude Desktop, Claude Code, Cursor, ChatGPT-style agents, custom agents) query the monitor's canonical data instead of guessing which consultations are open.

It reads the same `items.json` the website publishes, recomputes each item's status for today using the rules in `pipeline/models.py`, and exposes the result as MCP tools and resources. It never writes anything.

## Tools

| Tool | What it answers |
|---|---|
| `list_open(type?, topic?, lang?, limit?)` | Everything open right now, soonest closing first |
| `closing_soon(days=7, lang?)` | Open items closing within N days |
| `list_new(lang?)` | Items first seen or opened in the last 14 days |
| `search(query, include_retired?, lang?, limit?)` | Keyword search across titles, summaries, bodies and topics, in both languages |
| `get_item(id, lang?)` | Full record: summary, why it matters, how to participate, dates, link, `verified` flag |
| `list_topics()` | Topic tags in use, with open and total counts |
| `monitor_status()` | Counts by status, data source, fetch date, status rules |

`lang` is any language code configured in `data/site.yaml` (`en` and `fr` here; the primary is the default). Translated fields are returned when the store has them; otherwise the primary language falls through. An unconfigured code is an error.

## Resources

| URI | Content |
|---|---|
| `monitor://items` | All items as JSON, status recomputed for today |
| `monitor://items/{id}` | One item as JSON |
| `monitor://digest` | The latest weekly digest (Markdown, English) |
| `monitor://digest-<lang>` | The same digest in each secondary language (`monitor://digest-fr` here) |

## Install

```
pip install -r mcp_server/requirements.txt
python -m mcp_server.smoke_test      # offline check against site/items.json
python -m mcp_server                 # stdio server reading the live site
```

By default the server fetches `https://donjguido.github.io/ai-consultation-deadlines-canada/items.json` and caches it for ten minutes. To read a local checkout instead:

```
python -m mcp_server --items data/items.json
MONITOR_ITEMS=data/items.json python -m mcp_server
```

## Connect an assistant

**Claude Code** (from the repo root; the checked-in `.mcp.json` does the same thing automatically for anyone who opens the repo):

```
claude mcp add ai-governance-monitor -- python -m mcp_server
```

**Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "ai-governance-monitor": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "C:/path/to/ai-consultation-deadlines-canada"
    }
  }
}
```

Any other MCP host uses the same command. Once connected, ask things like "What AI consultations in Canada close this month?" or "How do I make a submission on the ISED transparency consultation?" and the assistant will call the tools above.

## Remote (HTTP) mode

The server can also speak streamable HTTP for hosts that cannot spawn a local process:

```
python -m mcp_server --http --host 0.0.0.0 --port 8765     # endpoint: http://host:8765/mcp
```

GitHub Pages cannot run it, so remote mode needs a small always-on host (a free-tier container or a $5/month VPS). It is not part of the pilot budget; the local stdio server costs nothing to run because it just reads the public JSON. Add authentication before exposing it publicly; the server ships with none.

## Caveats

- Items with `verified: false` were machine-classified and not yet checked by a human. The server says so in its instructions, and `get_item` returns the flag. Assistants should tell users to confirm dates on the source page.
- Data refreshes when the site is rebuilt (Mondays and Thursdays). Status is recomputed on every call, so an item that closed on Wednesday shows as retired on Saturday even before the next rebuild.
- The server is deliberately thin. New capabilities should come from the store, not from logic that only exists in the MCP layer.
