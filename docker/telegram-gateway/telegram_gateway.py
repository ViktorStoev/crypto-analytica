from __future__ import annotations

import os
import select
import socket
import socketserver
import struct
import sys
import time
import traceback
from typing import Final


LISTEN_HOST: Final[str] = os.getenv(
    "TELEGRAM_GATEWAY_HOST",
    "0.0.0.0",
)

LISTEN_PORT: Final[int] = int(
    os.getenv(
        "TELEGRAM_GATEWAY_PORT",
        "8080",
    )
)

ALLOWED_HOST: Final[str] = os.getenv(
    "TELEGRAM_GATEWAY_ALLOWED_HOST",
    "api.telegram.org",
).lower()

ALLOWED_PORT: Final[int] = int(
    os.getenv(
        "TELEGRAM_GATEWAY_ALLOWED_PORT",
        "443",
    )
)

UPSTREAM_SOCKS5_HOST: Final[str] = os.getenv(
    "TELEGRAM_GATEWAY_UPSTREAM_SOCKS5_HOST",
    "",
).strip()

UPSTREAM_SOCKS5_PORT_RAW: Final[str] = os.getenv(
    "TELEGRAM_GATEWAY_UPSTREAM_SOCKS5_PORT",
    "",
).strip()

UPSTREAM_SOCKS5_PORT: Final[int | None] = (
    int(UPSTREAM_SOCKS5_PORT_RAW)
    if UPSTREAM_SOCKS5_PORT_RAW
    else None
)

CONNECT_TIMEOUT_SECONDS: Final[float] = float(
    os.getenv(
        "TELEGRAM_GATEWAY_CONNECT_TIMEOUT",
        "20",
    )
)

RELAY_IDLE_TIMEOUT_SECONDS: Final[float] = float(
    os.getenv(
        "TELEGRAM_GATEWAY_RELAY_IDLE_TIMEOUT",
        "300",
    )
)

BUFFER_SIZE: Final[int] = 65536


def log(message: str) -> None:
    print(
        f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}",
        flush=True,
    )


class TelegramOnlyProxyHandler(
    socketserver.BaseRequestHandler
):
    def handle(self) -> None:
        client_address = self.client_address[0]

        try:
            self.request.settimeout(
                CONNECT_TIMEOUT_SECONDS
            )

            first_line = self._read_line()

            if not first_line:
                return

            method, target, http_version = self._parse_request_line(
                first_line
            )

            log(
                "CONNECT request: "
                f"client={client_address}, "
                f"method={method}, "
                f"target={target}, "
                f"version={http_version}"
            )

            if method.upper() != "CONNECT":
                self._send_response(
                    405,
                    "Method Not Allowed",
                    b"Only CONNECT is allowed.\n",
                )
                return

            host, port = self._parse_connect_target(
                target
            )

            if (
                host.lower() != ALLOWED_HOST
                or port != ALLOWED_PORT
            ):
                log(
                    "CONNECT denied: "
                    f"client={client_address}, "
                    f"target={host}:{port}"
                )

                self._drain_headers()

                self._send_response(
                    403,
                    "Forbidden",
                    (
                        b"This proxy is restricted to "
                        + ALLOWED_HOST.encode("utf-8")
                        + b":"
                        + str(ALLOWED_PORT).encode("ascii")
                        + b".\n"
                    ),
                )
                return

            self._drain_headers()

            log(
                "CONNECT allowed: "
                f"client={client_address}, "
                f"target={host}:{port}"
            )

            upstream = self._connect_upstream(
                host,
                port,
            )

            try:
                self.request.sendall(
                    b"HTTP/1.1 200 Connection Established\r\n"
                    b"Proxy-Agent: telegram-gateway\r\n"
                    b"\r\n"
                )

                log(
                    "Tunnel established: "
                    f"client={client_address}, "
                    f"target={host}:{port}"
                )

                self._relay(
                    self.request,
                    upstream,
                )

            finally:
                upstream.close()

                log(
                    "Tunnel closed: "
                    f"client={client_address}, "
                    f"target={host}:{port}"
                )

        except Exception as exc:
            log(
                "Gateway request failed: "
                f"client={client_address}, "
                f"error_type={type(exc).__name__}, "
                f"error={exc}"
            )

            traceback.print_exc(
                file=sys.stdout,
            )

            try:
                self._send_response(
                    502,
                    "Bad Gateway",
                    b"Telegram gateway upstream connection failed.\n",
                )
            except Exception:
                pass

    def _connect_upstream(
        self,
        host: str,
        port: int,
    ) -> socket.socket:
        if UPSTREAM_SOCKS5_HOST and UPSTREAM_SOCKS5_PORT:
            return self._connect_via_socks5(
                host,
                port,
                UPSTREAM_SOCKS5_HOST,
                UPSTREAM_SOCKS5_PORT,
            )

        return self._connect_direct_ipv4(
            host,
            port,
        )

    def _connect_via_socks5(
        self,
        target_host: str,
        target_port: int,
        socks_host: str,
        socks_port: int,
    ) -> socket.socket:
        log(
            "Connecting through SOCKS5: "
            f"socks={socks_host}:{socks_port}, "
            f"target={target_host}:{target_port}"
        )

        sock = socket.create_connection(
            (socks_host, socks_port),
            timeout=CONNECT_TIMEOUT_SECONDS,
        )

        sock.settimeout(
            CONNECT_TIMEOUT_SECONDS
        )

        # Greeting:
        # VER=5, NMETHODS=1, METHOD=0x00 no auth
        sock.sendall(b"\x05\x01\x00")

        response = self._recv_exact(
            sock,
            2,
        )

        if response != b"\x05\x00":
            sock.close()
            raise RuntimeError(
                "SOCKS5 server rejected no-auth method: "
                f"{response!r}"
            )

        host_bytes = target_host.encode("idna")

        if len(host_bytes) > 255:
            sock.close()
            raise RuntimeError(
                "SOCKS5 target hostname is too long."
            )

        # CONNECT request:
        # VER=5, CMD=1 CONNECT, RSV=0, ATYP=3 domain,
        # LEN, DOMAIN, PORT
        request = (
            b"\x05\x01\x00\x03"
            + bytes([len(host_bytes)])
            + host_bytes
            + struct.pack("!H", target_port)
        )

        sock.sendall(request)

        header = self._recv_exact(
            sock,
            4,
        )

        if len(header) != 4 or header[0] != 5:
            sock.close()
            raise RuntimeError(
                "Invalid SOCKS5 response header: "
                f"{header!r}"
            )

        reply_code = header[1]
        address_type = header[3]

        if reply_code != 0:
            sock.close()
            raise RuntimeError(
                "SOCKS5 CONNECT failed: "
                f"reply_code={reply_code}"
            )

        if address_type == 1:
            self._recv_exact(sock, 4)
        elif address_type == 3:
            domain_length = self._recv_exact(sock, 1)[0]
            self._recv_exact(sock, domain_length)
        elif address_type == 4:
            self._recv_exact(sock, 16)
        else:
            sock.close()
            raise RuntimeError(
                "Unsupported SOCKS5 address type: "
                f"{address_type}"
            )

        self._recv_exact(sock, 2)

        log(
            "SOCKS5 tunnel established: "
            f"target={target_host}:{target_port}"
        )

        sock.settimeout(None)

        return sock

    def _connect_direct_ipv4(
        self,
        host: str,
        port: int,
    ) -> socket.socket:
        log(
            "Resolving upstream IPv4: "
            f"{host}:{port}"
        )

        addresses = socket.getaddrinfo(
            host,
            port,
            socket.AF_INET,
            socket.SOCK_STREAM,
        )

        last_error: Exception | None = None

        for family, socktype, proto, canonname, sockaddr in addresses:
            ip_address = sockaddr[0]

            log(
                "Trying upstream IPv4: "
                f"{ip_address}:{port}"
            )

            upstream = socket.socket(
                family,
                socktype,
                proto,
            )

            upstream.settimeout(
                CONNECT_TIMEOUT_SECONDS
            )

            try:
                upstream.connect(sockaddr)

                log(
                    "Upstream connected: "
                    f"{ip_address}:{port}"
                )

                upstream.settimeout(None)

                return upstream

            except Exception as exc:
                last_error = exc

                log(
                    "Upstream connect failed: "
                    f"{ip_address}:{port}, "
                    f"error_type={type(exc).__name__}, "
                    f"error={exc}"
                )

                upstream.close()

        raise RuntimeError(
            "Could not connect to any IPv4 upstream address "
            f"for {host}:{port}. Last error: {last_error}"
        )

    def _recv_exact(
        self,
        sock: socket.socket,
        length: int,
    ) -> bytes:
        data = b""

        while len(data) < length:
            chunk = sock.recv(
                length - len(data)
            )

            if not chunk:
                raise RuntimeError(
                    "Unexpected EOF while reading from socket."
                )

            data += chunk

        return data

    def _read_line(self) -> bytes:
        data = b""

        while not data.endswith(b"\r\n"):
            chunk = self.request.recv(1)

            if not chunk:
                break

            data += chunk

            if len(data) > 8192:
                raise ValueError(
                    "Request line is too long."
                )

        return data.strip()

    def _parse_request_line(
        self,
        line: bytes,
    ) -> tuple[str, str, str]:
        parts = line.decode(
            "ascii",
            errors="replace",
        ).split()

        if len(parts) != 3:
            raise ValueError(
                "Invalid HTTP request line."
            )

        return parts[0], parts[1], parts[2]

    def _parse_connect_target(
        self,
        target: str,
    ) -> tuple[str, int]:
        if ":" not in target:
            raise ValueError(
                "CONNECT target must include port."
            )

        host, port_text = target.rsplit(
            ":",
            1,
        )

        return host.strip().lower(), int(port_text)

    def _drain_headers(self) -> None:
        while True:
            line = self._read_line()

            if line in {
                b"",
                b"\r\n",
            }:
                return

    def _send_response(
        self,
        status_code: int,
        reason: str,
        body: bytes,
    ) -> None:
        response = (
            f"HTTP/1.1 {status_code} {reason}\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("ascii") + body

        self.request.sendall(response)

    def _relay(
        self,
        client: socket.socket,
        upstream: socket.socket,
    ) -> None:
        sockets = [
            client,
            upstream,
        ]

        while True:
            readable, _, errored = select.select(
                sockets,
                [],
                sockets,
                RELAY_IDLE_TIMEOUT_SECONDS,
            )

            if errored:
                return

            if not readable:
                return

            for source in readable:
                data = source.recv(BUFFER_SIZE)

                if not data:
                    return

                destination = (
                    upstream
                    if source is client
                    else client
                )

                destination.sendall(data)


class ThreadingTCPServer(
    socketserver.ThreadingMixIn,
    socketserver.TCPServer,
):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    upstream_mode = (
        f"socks5://{UPSTREAM_SOCKS5_HOST}:{UPSTREAM_SOCKS5_PORT}"
        if UPSTREAM_SOCKS5_HOST and UPSTREAM_SOCKS5_PORT
        else "direct"
    )

    log(
        "Telegram gateway starting: "
        f"listen={LISTEN_HOST}:{LISTEN_PORT}, "
        f"allowed={ALLOWED_HOST}:{ALLOWED_PORT}, "
        f"upstream_mode={upstream_mode}, "
        f"connect_timeout={CONNECT_TIMEOUT_SECONDS}"
    )

    with ThreadingTCPServer(
        (LISTEN_HOST, LISTEN_PORT),
        TelegramOnlyProxyHandler,
    ) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()