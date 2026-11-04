import asyncio
import json
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit


class RuntimeState:
    def __init__(self):
        self.started_at = time.monotonic()
        self.ready = False
        self.cron_hits = 0
        self.last_cron_ping = None

    def payload(self):
        return {
            "service": "Kingdram",
            "status": "ok" if self.ready else "starting",
            "uptime_seconds": int(time.monotonic() - self.started_at),
            "cron_hits": self.cron_hits,
            "last_cron_ping": self.last_cron_ping,
        }


async def _handle_request(reader, writer, state):
    status_code = 200
    reason = "OK"
    body = {}
    parts = []

    try:
        request_line = await asyncio.wait_for(reader.readline(), timeout=8)
        if not request_line:
            return

        parts = request_line.decode("latin-1").strip().split()
        if len(parts) != 3:
            status_code, reason = 400, "Bad Request"
            body = {"status": "error", "message": "Solicitud HTTP no válida."}
        else:
            method, raw_path, _ = parts
            path = urlsplit(raw_path).path

            while True:
                header = await asyncio.wait_for(reader.readline(), timeout=8)
                if header in (b"\r\n", b"\n", b""):
                    break

            if method not in ("GET", "HEAD"):
                status_code, reason = 405, "Method Not Allowed"
                body = {
                    "status": "error",
                    "message": "Método no permitido. Usa GET.",
                }
            elif path in ("/", "/health", "/cron"):
                if path == "/cron" and state.ready:
                    state.cron_hits += 1
                    state.last_cron_ping = datetime.now(
                        timezone.utc
                    ).isoformat()

                if state.ready:
                    body = state.payload()
                else:
                    status_code, reason = 503, "Service Unavailable"
                    body = {
                        "service": "Kingdram",
                        "status": "starting",
                        "message": "El bot todavía está inicializándose.",
                    }
            else:
                status_code, reason = 404, "Not Found"
                body = {
                    "status": "not_found",
                    "message": "Ruta no encontrada.",
                    "available_routes": ["/", "/health", "/cron"],
                }

        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = [
            f"HTTP/1.1 {status_code} {reason}",
            "Content-Type: application/json; charset=utf-8",
            f"Content-Length: {len(encoded)}",
            "Cache-Control: no-store",
            "Connection: close",
        ]

        writer.write(("\r\n".join(headers) + "\r\n\r\n").encode("latin-1"))
        if len(parts) == 3 and parts[0] != "HEAD":
            writer.write(encoded)
        await writer.drain()

    except (asyncio.TimeoutError, ConnectionError, UnicodeDecodeError):
        pass
    except Exception as exc:
        print(f"Error atendiendo petición HTTP: {exc}")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def start_health_server(state):
    port = int(os.getenv("PORT", "10000"))
    server = await asyncio.start_server(
        lambda reader, writer: _handle_request(reader, writer, state),
        host="0.0.0.0",
        port=port,
        limit=8192,
    )

    print(f"Servidor HTTP de Kingdram escuchando en 0.0.0.0:{port}")
    print("Health check disponible en /health")
    print("Ping externo disponible en /cron")
    return server
