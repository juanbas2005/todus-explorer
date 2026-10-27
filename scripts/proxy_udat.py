#!/usr/bin/env python3
"""
Proxy HTTP/SOCKS5 ultra-simple que:
1. Acepta conexiones en localhost:8118
2. S3 → rutea via udyat (152.207.206.86)
3. Todo lo demás → directo normal

Cómo funciona:
  navegador → proxy:8118 → si es s3.todus.cu → via udyat
                               → si no → directo

Usa este en lugar de proxy_vpn.py si NO tienes un VPS externo.
Solo necesitas un servidor externo con SOCKS5.
"""
import socket, threading, select, struct, time, sys
from urllib.parse import urlparse

# ─── Configuración ──────────────────────────────────────
LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 8118

# Dominios zero-rated (rutean via udyat)
UDYAT_HOSTS = {"s3.todus.cu", "cdn.todus.cu"}

# ─────────────────────────────────────────────────────────

log = lambda m: print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

def pipe(a, b):
    while True:
        r, _, e = select.select([a, b], [], [a, b], 60)
        if e or not r:
            break
        for s in r:
            try:
                d = s.recv(8192)
                if not d:
                    return
                (b if s is a else a).sendall(d)
            except:
                return

def handle_http(client, method, path, headers, body):
    """Manejar request HTTP CONNECT o normal"""
    if method == "CONNECT":
        # CONNECT host:port → crear túnel
        host, port = path.split(":")
        port = int(port)

        use_udyat = host in UDYAT_HOSTS

        if use_udyat:
            # TODO: conectar via SSH tunnel a VPS con udyat
            # Por ahora: conectar directo via IP udyat
            log(f"CONNECT udyat: {host}:{port}")
            target = socket.socket()
            target.settimeout(30)
            try:
                target.connect(("152.207.206.86", 443))
                client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            except Exception as e:
                log(f"CONNECT udyat FAIL {host}:{e}")
                client.close()
                target.close()
                return

            pipe(client, target)
            target.close()
        else:
            # Directo
            log(f"CONNECT directo: {host}:{port}")
            target = socket.socket()
            target.settimeout(15)
            try:
                target.connect((host, port))
                client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            except Exception as e:
                log(f"CONNECT FAIL: {e}")
                client.close()
                target.close()
                return
            pipe(client, target)
            target.close()

    else:
        # HTTP normal (GET, POST, etc.)
        if path.startswith("http"):
            parsed = urlparse(path)
            host = parsed.netloc
            use_udyat = host in UDYAT_HOSTS
            target_path = parsed.path + ("?" + parsed.query if parsed.query else "")
        else:
            host = headers.get("Host", "")
            use_udyat = host.split(":")[0] in UDYAT_HOSTS
            target_path = path

        log(f"{method} {'[udyat] ' if use_udyat else ''}{host}{target_path}")

        target = socket.socket()
        target.settimeout(15)
        try:
            target.connect((host, 80))
            req = f"{method} {target_path} HTTP/1.1\r\n"
            for k, v in headers.items():
                req += f"{k}: {v}\r\n"
            if body:
                target.sendall(req.encode() + b"\r\n" + body)
            else:
                target.sendall(req.encode() + b"\r\n")
            # Pipe
            pipe(target, client)
            target.close()
        except Exception as e:
            log(f"HTTP FAIL {host}: {e}")
            target.close()
            client.close()

def read_headers(sock):
    headers = {}
    body_start = 0
    while True:
        line = sock.recv(1)
        if line == b"":
            break
        if line == b"\n":
            body_start = sock.tell() if hasattr(sock, "tell") else 0
            break
    return headers

def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((LISTEN_HOST, LISTEN_PORT))
    srv.listen(128)

    print("╔════════════════════════════════════════════════╗")
    print("║     proxy_udat.py — Proxy HTTP/SOCKS5 local   ║")
    print(f"║  Escuchando: {LISTEN_HOST}:{LISTEN_PORT}                      ║")
    print(f"║  Udyat: {', '.join(sorted(UDYAT_HOSTS))}  ║")
    print("╠════════════════════════════════════════════════╣")
    print("║  Configura en tu navegador:                  ║")
    print(f"║    HTTP Proxy → {LISTEN_HOST}:{LISTEN_PORT}                  ║")
    print("╚════════════════════════════════════════════════╝")
    print()

    try:
        while True:
            client, addr = srv.accept()
            t = threading.Thread(target=handle_conn, args=(client,), daemon=True)
            t.start()
    except KeyboardInterrupt:
        print("\nDeteniendo...")
    finally:
        srv.close()

if __name__ == "__main__":
    main()