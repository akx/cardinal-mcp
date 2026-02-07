import asyncio
import json
import logging
import struct
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)


def _pad4(n: int) -> int:
    return (4 - (n % 4)) % 4


def _encode_string(value: str) -> bytes:
    data = value.encode("utf-8") + b"\x00"
    return data + (b"\x00" * _pad4(len(data)))


def _encode_arg(value: Any, arg_type: str) -> bytes:
    if arg_type == "s":
        return _encode_string(str(value))
    if arg_type == "i":
        return struct.pack(">i", int(value))
    if arg_type == "h":
        return struct.pack(">q", int(value))
    if arg_type == "f":
        return struct.pack(">f", float(value))
    if arg_type == "b":
        data = bytes(value)
        return struct.pack(">i", len(data)) + data + (b"\x00" * _pad4(len(data)))
    raise ValueError(f"Unsupported OSC arg type: {arg_type}")


def build_message(address: str, args: list[tuple[Any, str]]) -> bytes:
    addr = _encode_string(address)
    types = "," + "".join(arg_type for _value, arg_type in args)
    type_tag = _encode_string(types)
    payload = b"".join(_encode_arg(value, arg_type) for value, arg_type in args)
    return addr + type_tag + payload


def _decode_string(data: bytes, offset: int) -> tuple[str, int]:
    end = data.find(b"\x00", offset)
    if end < 0:
        return "", len(data)
    value = data[offset:end].decode("utf-8", errors="replace")
    end = end + 1
    end += _pad4(end)
    return value, end


def _decode_arg(data: bytes, offset: int, arg_type: str) -> tuple[Any, int]:
    if arg_type == "s":
        return _decode_string(data, offset)
    if arg_type == "i":
        return struct.unpack_from(">i", data, offset)[0], offset + 4
    if arg_type == "h":
        return struct.unpack_from(">q", data, offset)[0], offset + 8
    if arg_type == "f":
        return struct.unpack_from(">f", data, offset)[0], offset + 4
    return None, offset


def _parse_message(data: bytes) -> tuple[str, str, list[Any]] | None:
    address, offset = _decode_string(data, 0)
    if not address:
        return None
    types, offset = _decode_string(data, offset)
    if not types or not types.startswith(","):
        return address, "", []
    types = types[1:]
    args = []
    for t in types:
        value, offset = _decode_arg(data, offset, t)
        args.append(value)
    return address, types, args


def _load_json(payload: str) -> dict[str, Any]:
    return json.loads(payload)


class _StreamCollector:
    def __init__(self, msg: str, item_key: str):
        self._msg = msg
        self.items: list[Any] = []
        self._item_key = item_key
        self._total: int | None = None
        self._last_index: int | None = None

    def handle(self, payload: str) -> None:
        data = _load_json(payload)
        item = data.get(self._item_key)
        if item:
            self.items.append(item)
        index = data.get("index")
        if index is not None:
            self._last_index = index
        total = data.get("total")
        if total is not None:
            self._total = total

    def done(self) -> bool:
        if self._total is None:
            return False
        if self._total == 0:
            return True
        if self._last_index is not None:
            return self._last_index + 1 >= self._total
        return len(self.items) >= self._total

    async def collect(self, client: "CardinalOSCClient") -> list[Any]:
        try:
            while True:
                recv_msg, payload = await asyncio.wait_for(client._recv_queue.get(), timeout=client.timeout)
                if recv_msg != self._msg:
                    continue
                self.handle(payload)
                if self.done():
                    return list(self.items)
        except TimeoutError as exc:
            raise TimeoutError(f"Timed out waiting for /{self._msg.replace('-', '/')} response") from exc


class _OSCProtocol(asyncio.DatagramProtocol):
    def __init__(self, handler: Callable[[bytes, tuple[str, int]], None]):
        self._handler = handler

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self._handler(data, addr)


class CardinalOSCClient:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 2228,
        local_port: int = 9000,
        timeout: float = 2.0,
    ):
        self.host = host
        self.port = port
        self.local_port = local_port
        self.timeout = timeout

        self.modules: list[dict[str, Any]] = []
        self.available_modules: list[dict[str, Any]] = []

        self._transport: asyncio.DatagramTransport | None = None
        self._recv_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

    async def start(self) -> None:
        if self._transport is not None:
            return
        loop = asyncio.get_running_loop()
        self._transport, _protocol = await loop.create_datagram_endpoint(
            lambda: _OSCProtocol(self._on_datagram),
            local_addr=("0.0.0.0", self.local_port),
        )

    def close(self) -> None:
        if self._transport is None:
            return
        self._transport.close()
        self._transport = None

    def send(self, address: str, args: list[tuple[Any, str]]) -> None:
        if self._transport is None:
            raise RuntimeError("OSC transport not started")
        dgram = build_message(address, args)
        log.debug("send %s types=%s", address, "," + "".join(arg_type for _value, arg_type in args))
        self._transport.sendto(dgram, (self.host, self.port))

    async def hello(self) -> None:
        self.send("/hello", [])
        await self._await_payload("hello", lambda payload: payload == "ok", "Timed out waiting for /hello response")

    async def refresh_modules(self) -> list[dict[str, Any]]:
        self.send("/modules/list", [])
        self.modules = await _StreamCollector("modules", "module").collect(self)
        return list(self.modules)

    async def refresh_available(self) -> list[dict[str, Any]]:
        self.send("/modules/available", [])
        self.available_modules = await _StreamCollector("modules-available", "module").collect(self)
        return list(self.available_modules)

    async def add_module(self, plugin: str, model: str, pos_x: int | None = None, pos_y: int | None = None) -> int:
        if pos_x is not None and pos_y is not None:
            self.send("/module/add", [(plugin, "s"), (model, "s"), (pos_x, "i"), (pos_y, "i")])
        else:
            self.send("/module/add", [(plugin, "s"), (model, "s")])
        payload = await self._await_payload("module-add", lambda _p: True, "Timed out waiting for /module/add response")
        data = _load_json(payload)
        module_id = data.get("id") if isinstance(data, dict) else None
        if module_id is None:
            raise RuntimeError("Unable to determine new module id from /module/add")
        return module_id

    async def remove_module(self, module_id: int) -> int | None:
        self.send("/module/remove", [(module_id, "h")])
        payload = await self._await_payload("module-remove", lambda _p: True, "Timed out waiting for /module/remove response")
        data = _load_json(payload)
        if isinstance(data, dict):
            return data.get("id")
        return None

    async def module_params(self, module_id: int) -> list[dict[str, Any]]:
        self.send("/module/params", [(module_id, "h")])
        return await _StreamCollector("module-params", "param").collect(self)

    async def module_inputs(self, module_id: int) -> list[dict[str, Any]]:
        self.send("/module/inputs", [(module_id, "h")])
        return await _StreamCollector("module-inputs", "input").collect(self)

    async def module_outputs(self, module_id: int) -> list[dict[str, Any]]:
        self.send("/module/outputs", [(module_id, "h")])
        return await _StreamCollector("module-outputs", "output").collect(self)

    async def cable_add(self, output_module_id: int, output_id: int, input_module_id: int, input_id: int) -> int:
        state: dict[str, Any] = {"value": None, "error": None}

        def handler(payload: str) -> None:
            data = _load_json(payload)
            cable_id = data.get("id")
            if cable_id is not None:
                state["value"] = cable_id
            else:
                state["error"] = data.get("error") or "unknown"

        self.send(
            "/cable/add",
            [
                (output_module_id, "h"),
                (int(output_id), "i"),
                (input_module_id, "h"),
                (int(input_id), "i"),
            ],
        )
        payload = await self._await_payload("cable-add", lambda _p: True, "Timed out waiting for /cable/add response")
        handler(payload)
        if state["value"] is None:
            raise RuntimeError(f"/cable/add failed: {state['error']}")
        return state["value"]

    async def cable_remove(self, cable_id: int) -> int | None:
        self.send("/cable/remove", [(cable_id, "h")])
        payload = await self._await_payload("cable-remove", lambda _p: True, "Timed out waiting for /cable/remove response")
        data = _load_json(payload)
        if isinstance(data, dict):
            return data.get("id")
        return None

    async def cables_list(self, module_id: int | None = None) -> list[dict[str, Any]]:
        if module_id is not None:
            self.send("/cables/list", [(module_id, "h")])
        else:
            self.send("/cables/list", [])
        return await _StreamCollector("cables", "cable").collect(self)

    async def module_info(self, module_id: int) -> dict[str, Any]:
        self.send("/module/info", [(module_id, "h")])
        payload = await self._await_payload("module-info", lambda _p: True, "Timed out waiting for /module/info response")
        data = _load_json(payload)
        if isinstance(data, dict) and data.get("module"):
            return data["module"]
        raise RuntimeError(f"/module/info failed: {data.get('error', 'unknown') if isinstance(data, dict) else 'unknown'}")

    def set_param(self, module_id: int, param_id: int, value: float) -> None:
        self.send("/param", [(module_id, "h"), (param_id, "i"), (value, "f")])

    def set_host_param(self, param_id: int, value: float) -> None:
        self.send("/host-param", [(param_id, "i"), (value, "f")])

    async def load(self, data: bytes) -> None:
        self.send("/load", [(data, "b")])
        payload = await self._await_payload("load", lambda p: p in ("ok", "fail"), "Timed out waiting for /load response")
        if payload != "ok":
            raise RuntimeError("/load failed")

    async def _await_payload(self, msg: str, predicate: Callable[[str], bool], timeout_message: str) -> str:
        try:
            while True:
                recv_msg, payload = await asyncio.wait_for(self._recv_queue.get(), timeout=self.timeout)
                if recv_msg != msg:
                    continue
                if predicate(payload):
                    return payload
        except TimeoutError as exc:
            raise TimeoutError(timeout_message) from exc

    def _on_datagram(self, data: bytes, _addr: tuple[str, int]) -> None:
        parsed = _parse_message(data)
        if not parsed:
            return
        address, _types, args = parsed
        if address != "/resp" or len(args) < 2:
            return
        msg, payload = args[0], args[1]
        log.debug("/resp %s %s", msg, payload)
        self._recv_queue.put_nowait((msg, payload))
