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


def _module_matches(module: dict, query: str) -> bool:
    for key in ("name", "plugin", "model", "description", "slug"):
        val = module.get(key, "")
        if val and query in str(val).lower():
            return True
    tags = module.get("tags")
    if isinstance(tags, list):
        for tag in tags:
            if query in str(tag).lower():
                return True
    elif isinstance(tags, str) and query in tags.lower():
        return True
    return False


@mcp.tool()
async def search_for_available_module(query: str) -> list[dict]:
    """Search for available modules by name, plugin, model, description, slug, or tags. Case-insensitive substring match."""
    c = await get_osc_client()
    query_lower = query.lower()
    return [m for m in c.available_modules if _module_matches(m, query_lower)]


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
async def add_cables(cables: list[dict]) -> list[dict]:
    """Add multiple cables in one call.

    Each entry should be a dict with keys: source_module_id, source_output_id, target_module_id, target_input_id (all ints).
    Returns a list of results, each with cable_id on success or error on failure. Continues after failures.
    """
    c = await get_osc_client()
    results = []
    for i, cab in enumerate(cables):
        try:
            cable_id = await c.cable_add(
                int(cab["source_module_id"]),
                int(cab["source_output_id"]),
                int(cab["target_module_id"]),
                int(cab["target_input_id"]),
            )
            results.append({"index": i, "cable_id": cable_id})
        except Exception as e:
            results.append({"index": i, "error": str(e)})
    return results


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
async def set_params(params: list[dict]) -> int:
    """Set multiple parameter values in one call.

    Each entry in params should be a dict with keys: module_id (int), param_id (int), value (float).
    Returns the number of parameters set.
    """
    c = await get_osc_client()
    count = 0
    for p in params:
        c.set_param(int(p["module_id"]), int(p["param_id"]), float(p["value"]))
        count += 1
    return count


@mcp.tool()
async def set_host_param(param_id: int, value: float) -> None:
    """Set a host parameter value.

    Known host parameter IDs:
    - 0: Reset (1.0 to trigger)
    - 1: BPM (e.g. 120.0)
    - 2: Play (1.0 = play, 0.0 = stop)
    """
    c = await get_osc_client()
    c.set_host_param(param_id, value)


@mcp.tool()
async def get_module_full_info(module_id: int) -> dict:
    """Get complete info about a module in one call: info, params, inputs, and outputs."""
    c = await get_osc_client()
    info = await c.module_info(module_id)
    params = await c.module_params(module_id)
    inputs = await c.module_inputs(module_id)
    outputs = await c.module_outputs(module_id)
    return {"info": info, "params": params, "inputs": inputs, "outputs": outputs}


@mcp.tool()
async def get_patch_state(
    module_ids: list[int] | None = None,
    include_params: bool = True,
    include_inputs: bool = True,
    include_outputs: bool = True,
) -> dict:
    """Get the full state of the current patch in one call.

    Returns modules, cables, and detailed info (params, inputs, outputs) for every module.
    This replaces the need for separate get_modules + get_cables + N * get_module_params/inputs/outputs calls.

    For large patches, use the filtering options to reduce response size:
    - module_ids: Only include details for these specific module IDs (cables and module list are always complete).
    - include_params/include_inputs/include_outputs: Set to false to omit that section from module details.
    """
    c = await get_osc_client()
    modules = await c.refresh_modules()
    cables = await c.cables_list()
    module_details = {}
    for mod in modules:
        mid = mod.get("id")
        if mid is None:
            continue
        if module_ids is not None and mid not in module_ids:
            continue
        detail: dict = {}
        if include_params:
            detail["params"] = await c.module_params(mid)
        if include_inputs:
            detail["inputs"] = await c.module_inputs(mid)
        if include_outputs:
            detail["outputs"] = await c.module_outputs(mid)
        module_details[str(mid)] = detail
    return {"modules": modules, "cables": cables, "module_details": module_details}


@mcp.tool()
async def load_patch(data: str) -> None:
    """Load a patch from base64-encoded patch archive data."""
    c = await get_osc_client()
    await c.load(base64.b64decode(data))


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
