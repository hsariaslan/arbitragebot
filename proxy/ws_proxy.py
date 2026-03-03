#!/usr/bin/env python3
"""Generic WebSocket proxy — transparent bidirectional relay.

Usage:
    python ws_proxy.py --target wss://api-pub.bitfinex.com/ws/2 --port 9000
    python ws_proxy.py --target wss://stream.binance.com:9443/stream --port 9001

Each incoming client connection spawns a corresponding upstream connection.
All messages (text and binary) are forwarded without modification.
Connection close on either side propagates to the other.
"""

import argparse
import asyncio
import logging
import signal

import websockets

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger("ws-proxy")


async def _forward(src, dst):
    """Forward all messages from src to dst until either side closes."""
    try:
        async for msg in src:
            await dst.send(msg)
    except websockets.ConnectionClosed:
        pass


async def _handle_client(client_ws, target_url):
    """Handle one client: connect upstream, relay bidirectionally."""
    peer = client_ws.remote_address
    logger.info("Client connected: %s:%s", peer[0], peer[1])

    try:
        async with websockets.connect(
            target_url,
            ping_interval=None,
            ping_timeout=None,
            close_timeout=10,
            max_size=2**20,
        ) as upstream_ws:
            logger.info("Upstream connected for %s:%s", peer[0], peer[1])

            c2u = asyncio.create_task(_forward(client_ws, upstream_ws))
            u2c = asyncio.create_task(_forward(upstream_ws, client_ws))

            done, pending = await asyncio.wait(
                [c2u, u2c], return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass

    except Exception as exc:
        logger.error("Upstream failed for %s:%s: %s", peer[0], peer[1], exc)
    finally:
        try:
            await client_ws.close()
        except Exception:
            pass
        logger.info("Client disconnected: %s:%s", peer[0], peer[1])


async def main(target_url, port, host):
    logger.info("Starting proxy: %s:%d -> %s", host, port, target_url)

    stop = asyncio.Future()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set_result, None)

    async with websockets.serve(
        lambda ws: _handle_client(ws, target_url),
        host,
        port,
        ping_interval=None,
        ping_timeout=None,
        close_timeout=10,
        max_size=2**20,
    ):
        logger.info("Proxy listening on ws://%s:%d", host, port)
        await stop

    logger.info("Proxy shut down")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generic WebSocket proxy")
    parser.add_argument(
        "--target", required=True, help="Upstream WebSocket URL",
    )
    parser.add_argument(
        "--port", type=int, default=9000, help="Listen port (default: 9000)",
    )
    parser.add_argument(
        "--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.target, args.port, args.host))
