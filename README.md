# cardinal-mcp

An [MCP](https://modelcontextprotocol.io/) server that lets LLMs control [Cardinal](https://github.com/DISTRHO/Cardinal), the open-source virtual modular synthesizer, via OSC.

## Features

- Add/remove modules and cables
- Query module parameters, inputs, and outputs
- Search the available module catalog
- Set module and host parameters
- Load patches

> [!NOTE]
> Most of the OSC commands used by this server are not yet in upstream Cardinal.
> You'll need the [`more-osc-capabilities`](https://github.com/akx/Cardinal/tree/more-osc-capabilities) branch.

## Requirements

- Python >= 3.11
- A running Cardinal instance with OSC enabled (default port 2228)

## Quickstart

```bash
uv run cardinal_mcp.py
```

The MCP server starts on port 9109 using streamable HTTP transport.

## Using with Claude Code

With the server running, add it as a remote MCP server:

```bash
claude mcp add cardinal-mcp --transport http http://localhost:9109/mcp
```

Then try a prompt like:

> Search for a VCO module, add it to the rack, and connect it to the Audio output module.

## License

MIT