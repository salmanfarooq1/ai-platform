"""A tiny HTTP endpoint for the worker's own metrics (`WORKER_METRICS_PORT`, off when 0).

Decisions that an agent run causes are recorded in the worker, so the worker counts them. Prometheus scrapes this port
the same way it scrapes the API. It answers `GET /metrics` with the text format and 404 to everything else. It binds
to all interfaces because a container scrape needs that: do not publish the port outside the compose network.
"""
import asyncio
import logging

from core.database.tenant import DbPool
from core.metrics import CONTENT_TYPE, get_metrics

logger = logging.getLogger("workers.metrics")


async def start_metrics_server(pool: DbPool, port: int) -> asyncio.AbstractServer:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line = (await asyncio.wait_for(reader.readline(), 5.0)).decode("latin-1")
            while (await asyncio.wait_for(reader.readline(), 5.0)) not in (b"\r\n", b"\n", b""):
                pass  # skip the headers
            if request_line.startswith("GET /metrics"):
                collector = get_metrics()
                await collector.refresh_from_database(pool)
                body = collector.render()
                head = f"HTTP/1.1 200 OK\r\nContent-Type: {CONTENT_TYPE}\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n"
                writer.write(head.encode() + body)
            else:
                writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            await writer.drain()
        except (asyncio.TimeoutError, ConnectionError):
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(handle, "0.0.0.0", port)  # noqa: S104 - a container scrape needs it
    logger.info("worker metrics served on port %d", port)
    return server
