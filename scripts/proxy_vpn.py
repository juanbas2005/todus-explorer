#!/usr/bin/env python3
"""
SOCKS5 Proxy local que rutea TODO el tráfico через VPS externo.
El VPS afuera rutea s3.todus.cu через udyat (IP zero-rated).

Cómo funciona:
  navegador → localhost:1080 (SOCKS5) → VPS externo → internet
                                              ↓
                                     s3.todus.cu via udyat
                                     (zero-rated, no gasta megas)
Para usarlo:
  1. python3 proxy_vpn.py
  2. Configura el navegador/proxy del sistema para usar SOCKS5 en localhost:1080
  3. TODO tu tráfico pasa por el VPS

NOTA: Solo rutea a través del VPS. El VPS ve TODO tu tráfico.
      USA BAJO TU PROPIO RIESGO.
"""
import socket, threading, select, struct, time

# ─── Configuración ───────────────────────────────────────
LISTEN_HOST = "127.0.0.1"   # Solo localhost (seguro)
LISTEN_PORT = 1080           # Puerto del proxy SOCKS5

# IP del VPS externo (el que recibirá el tráfico)
# EJEMPLO: cambia esto por la IP de TU VPS
# VPS便宜的: Oracle Cloud Free, AWS Free Tier, Google Cloud Free
VPS_HOST = "152.207.206.86"   # ← CAMBIA ESTO por la IP de tu VPS
VPS_PORT = 1080               # Puerto SOCKS5 del VPS (por defecto 1080)

# Dominios que van por udyat (zero-rated)
UDYAT_HOSTS = {"s3.todus.cu"}

# ─────────────────────────────────────────────────────────

LOG_ENABLED = True

def log(msg):
    if LOG_ENABLED:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def read_bytes(sock, n):
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            return data
        data += chunk
    return data

def handle_client(client_sock, client_addr):
    try:
        # ── SOCKS5 handshake (solo autentificación none) ──
        version = client_sock.recv(1)
        if not version or version[0] != 5:
            client_sock.close()
            return

        nmethods = client_sock.recv(1)
        if not nmethods:
            client_sock.close()
            return
        methods = client_sock.recv(nmethods[0])
        if b"\x00" not in methods:  # "no auth" no soportado
            client_sock.sendall(b"\x05\xff")
            client_sock.close()
            return
        client_sock.sendall(b"\x05\x00")  # OK, sin auth

        # ── Request ─────────────────────────────────────
        header = read_bytes(client_sock, 4)
        if not header or len(header) < 4:
            client_sock.close()
            return
        version, cmd, _, addr_type = header

        if cmd != 1:  # solo CONNECT
            client_sock.sendall(b"\x05\x07\x00\x01" + b"\x00" * 6)
            client_sock.close()
            return

        # Leer dirección
        if addr_type == 1:  # IPv4
            raw_addr = read_bytes(client_sock, 4)
            addr = socket.inet_ntoa(raw_addr)
        elif addr_type == 3:  # Domain
            length = client_sock.recv(1)[0]
            raw_addr = client_sock.recv(length)
            addr = raw_addr.decode()
        elif addr_type == 4:  # IPv6
            raw_addr = read_bytes(client_sock, 16)
            addr = socket.inet_ntop(socket.AF_INET6, raw_addr)
        else:
            client_sock.sendall(b"\x05\x08\x00\x01" + b"\x00" * 6)
            client_sock.close()
            return

        port = struct.unpack(">H", read_bytes(client_sock, 2))[0]

        # ── Conectar al VPS (destino final) ──────────────
        use_udyat = addr in UDYAT_HOSTS

        if use_udyat:
            # Dominio zero-rated → conectar al VPS que tiene udyat
            target_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_sock.settimeout(30)
            try:
                target_sock.connect((VPS_HOST, VPS_PORT))
            except Exception as e:
                log(f"udat CONECT FAIL {addr}:{port} → {e}")
                client_sock.close()
                target_sock.close()
                return

            # Enviar request original al VPS
            # El VPS necesita recibir el addr real
            req = header + (raw_addr if addr_type == 1 else bytes([length]) + raw_addr) + struct.pack(">H", port)
            target_sock.sendall(req)

            # Leer respuesta del VPS
            try:
                resp = target_sock.recv(10)
                client_sock.sendall(resp)
            except:
                pass

            log(f"udat → {addr}:{port} (via VPS udyat)")
        else:
            # Conexión normal → directo al VPS como relay
            target_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_sock.settimeout(30)
            try:
                target_sock.connect((VPS_HOST, VPS_PORT))
            except Exception as e:
                log(f"CONNECT FAIL {addr}:{port} → {e}")
                client_sock.close()
                target_sock.close()
                return

            # Reenviar request al VPS
            req = header + (raw_addr if addr_type == 1 else bytes([length]) + raw_addr) + struct.pack(">H", port)
            target_sock.sendall(req)

            # Reenviar respuesta
            try:
                resp = target_sock.recv(10)
                client_sock.sendall(resp)
            except:
                pass

            log(f"      {addr}:{port} (via VPS relay)")

        # ── Pipe bidireccional ──────────────────────────
        pipe(client_sock, target_sock)

    except Exception as e:
        log(f"ERROR {client_addr}: {e}")
    finally:
        try:
            client_sock.close()
        except:
            pass
        try:
            target_sock.close()
        except:
            pass

def pipe(s1, s2):
    """Pipe bidireccional eficiente con select()"""
    sockets = [s1, s2]
    while True:
        r, _, e = select.select(sockets, [], sockets, 60)
        if e or not r:
            break
        for s in r:
            try:
                data = s.recv(4096)
                if not data:
                    return
                other = s2 if s is s1 else s1
                other.sendall(data)
            except:
                return

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((LISTEN_HOST, LISTEN_PORT))
    server.listen(128)

    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║        SOCKS5 Proxy — proxy_vpn.py             ║")
    print("╠══════════════════════════════════════════════════╣")
    print(f"║  Escuchando: {LISTEN_HOST}:{LISTEN_PORT}                        ║")
    print(f"║  VPS relay:   {VPS_HOST}:{VPS_PORT}              ║")
    print(f"║  Udyat hosts: {', '.join(sorted(UDYAT_HOSTS))[:25]}  ║")
    print("╠══════════════════════════════════════════════════╣")
    print("║  Configura en tu navegador/SO:                   ║")
    print(f"║    SOCKS5 → {LISTEN_HOST}:{LISTEN_PORT}                   ║")
    print("║  Ctrl+C para detener                           ║")
    print("╚══════════════════════════════════════════════════╝")
    print()
    print("⚠  TODO el tráfico pasa por el VPS. USA CON CUIDADO.")
    print()

    try:
        while True:
            client, addr = server.accept()
            t = threading.Thread(target=handle_client, args=(client, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        print("\nDeteniendo proxy...")
    finally:
        server.close()

if __name__ == "__main__":
    main()
