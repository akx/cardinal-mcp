import base64
import random

from mcp.server.fastmcp import FastMCP

from cardinal_osc_client import CardinalOSCClient

mcp = FastMCP("Cardinal", json_response=True, port=9109, debug=True)

_osc_client: CardinalOSCClient | None = None


async def get_osc_client() -> CardinalOSCClient:
    global _osc_client
    if _osc_client is None:
        _osc_client = CardinalOSCClient(local_port=random.randint(10000, 60000))
        await _osc_client.start()
        await _osc_client.hello()
        await _osc_client.refresh_available()
    return _osc_client


@mcp.tool()
async def get_available_modules() -> list[dict]:
    """
    Get a list of available modules that can be added to the rack.
    """
    c = await get_osc_client()
    return c.available_modules


@mcp.tool()
async def get_modules() -> list[dict]:
    """
    Get a list of modules currently in the rack.
    """
    c = await get_osc_client()
    return await c.refresh_modules()


@mcp.tool()
async def get_module_inputs(module_id: int) -> list[dict]:
    """
    Get the inputs of a module.
    """
    c = await get_osc_client()
    return await c.module_inputs(module_id)


@mcp.tool()
async def get_module_outputs(module_id: int) -> list[dict]:
    """Get the outputs of a module."""
    c = await get_osc_client()
    return await c.module_outputs(module_id)


@mcp.tool()
async def get_module_info(module_id: int) -> dict:
    """Get detailed info about a module."""
    c = await get_osc_client()
    return await c.module_info(module_id)


@mcp.tool()
async def get_module_params(module_id: int) -> list[dict]:
    """Get the parameters of a module."""
    c = await get_osc_client()
    return await c.module_params(module_id)


@mcp.tool()
async def search_for_available_module(query: str) -> list[dict]:
    """Search for available modules by name. Case-insensitive substring match."""
    c = await get_osc_client()
    query_lower = query.lower()
    return [m for m in c.available_modules if query_lower in repr(m).lower()]


@mcp.tool()
async def add_module(plugin_name: str, model_name: str) -> str:
    """Add a module to the rack. Returns the module ID."""
    c = await get_osc_client()
    # Agents seem to have a weird idea of the coordinate system for pos_x/pos_y, so let's not set them for now.
    return str(await c.add_module(plugin=plugin_name, model=model_name, pos_x=None, pos_y=None))


@mcp.tool()
async def remove_module(module_id: int) -> None:
    """Remove a module from the rack."""
    c = await get_osc_client()
    await c.remove_module(module_id)


@mcp.tool()
async def add_cable(source_module_id: int, source_output_id: int, target_module_id: int, target_input_id: int) -> int:
    """Add a cable between two modules. Returns the cable ID."""
    c = await get_osc_client()
    return await c.cable_add(source_module_id, source_output_id, target_module_id, target_input_id)


@mcp.tool()
async def remove_cable(cable_id: int) -> None:
    """Remove a cable by its ID."""
    c = await get_osc_client()
    await c.cable_remove(cable_id)


@mcp.tool()
async def get_cables(module_id: int | None = None) -> list[dict]:
    """Get a list of cables. Optionally filter by module ID."""
    c = await get_osc_client()
    return await c.cables_list(module_id)


@mcp.tool()
async def set_param(module_id: int, param_id: int, value: float) -> None:
    """Set a parameter value on a module."""
    c = await get_osc_client()
    c.set_param(module_id, param_id, value)


@mcp.tool()
async def set_host_param(param_id: int, value: float) -> None:
    """Set a host parameter value."""
    c = await get_osc_client()
    c.set_host_param(param_id, value)


@mcp.tool()
async def load_patch(data: str) -> None:
    """Load a patch from base64-encoded patch archive data."""
    c = await get_osc_client()
    await c.load(base64.b64decode(data))


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
