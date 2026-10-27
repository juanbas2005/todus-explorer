#!/usr/bin/env python3
"""Servidor web para navegar y gestionar s3.todus.cu/stream desde el navegador.

  python3 scripts/s3_server.py
  Abre http://localhost:8080 en el navegador.
  🔗 copia enlaces · 🗑️ elimina · ▶ Ver videos en el navegador
"""
import http.server, json, os, signal, socketserver, ssl, subprocess, sys, urllib.parse, xml.etree.ElementTree as ET
from urllib.parse import quote
import socket as _socket

# ─── Config ───────────────────────────────────────────────────────────────────
BASE = "https://s3.todus.cu/stream"
S3S  = "https://s3.todus.cu/stream"

# Sistema UDYAT: IP zero-rated de ETECSA (no gasta megas en datos móviles de Cuba)
UDYAT_IP   = "152.207.206.86"
UDYAT_IP2  = "152.207.206.88"   # DNS actual / respaldo
TODUS_HOST = "s3.todus.cu"
# Render asigna PORT dinámicamente (10000 en free tier); default 8080 para local
PORT = int(os.environ.get("PORT", 8080))
HOST = os.environ.get("HOST", "0.0.0.0")
NS   = "http://s3.amazonaws.com/doc/2006-03-01/"

VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".m4v", ".flv", ".wmv", ".3gp", ".ogv"}

def is_video(key):
    return any(key.lower().endswith(e) for e in VIDEO_EXTS)

def mime_for_key(key):
    e = os.path.splitext(key)[-1].lower()
    return {
        ".mp4": "video/mp4", ".mkv": "video/x-matroska", ".webm": "video/webm",
        ".avi": "video/x-msvideo", ".mov": "video/quicktime", ".m4v": "video/x-m4v",
        ".flv": "video/x-flv", ".wmv": "video/x-ms-wmv", ".3gp": "video/3gpp",
        ".ogv": "video/ogg"
    }.get(e, "application/octet-stream")

# ─── S3 helpers ───────────────────────────────────────────────────────────────
def curl(url, method=None, extra=None):
    cmd = ["curl", "-sS", "-m", "30", url]
    if method: cmd += ["-X", method]
    if extra:  cmd += extra
    return subprocess.run(cmd, capture_output=True, text=True).stdout

def list_objects(prefix="", max_objects=2000):
    """Lista objetos ({key, size, mtime}) con paginación automática.

    Se detiene en max_objects para no eternizarse en buckets enormes.
    Devuelve (objs, truncated).
    """
    enc = quote(prefix, safe="")
    marker, objs, truncated = "", [], False
    while len(objs) < max_objects:
        url = f"{BASE}?list-type=2&prefix={enc}&max-keys=1000"
        if marker:
            url += f"&continuation-token={quote(marker)}"
        page = curl(url)
        try:
            root = ET.fromstring(page)
        except ET.ParseError:
            break
        for c in root.findall(f"{{{NS}}}Contents"):
            key_el = c.find(f"{{{NS}}}Key")
            if key_el is None or not key_el.text:
                continue
            size_el = c.find(f"{{{NS}}}Size")
            lm_el   = c.find(f"{{{NS}}}LastModified")
            objs.append({
                "key": key_el.text,
                "size": int(size_el.text) if size_el is not None and size_el.text else None,
                "mtime": lm_el.text if lm_el is not None else None,
            })
            if len(objs) >= max_objects:
                truncated = True
                break
        trunc = root.find(f"{{{NS}}}IsTruncated")
        nxt   = root.find(f"{{{NS}}}NextContinuationToken")
        if truncated or trunc is None or trunc.text != "true" or nxt is None or not nxt.text:
            break
        marker = nxt.text
    return objs, truncated

def list_keys(prefix=""):
    objs, _ = list_objects(prefix)
    return [o["key"] for o in objs]

# ─── Conexiones UDYAT (socket TLS directo, sin curl) ─────────────────────────
def _http_get_request(path, range_header, host):
    req = (f"GET {path} HTTP/1.1\r\n"
           f"Host: {host}\r\n"
           f"User-Agent: Wget/1.21.3\r\n"          # UA exacto del sistema UDYAT
           f"Accept: */*\r\n"
           f"Accept-Encoding: identity\r\n")       # sin gzip: streaming limpio
    if range_header:
        req += f"Range: {range_header}\r\n"
    req += "Connection: close\r\n\r\n"
    return req.encode()

def open_udyat_conn(path, range_header=None, timeout=5):
    """Abre TLS directo a la IP zero-rated con SNI/Host correctos.

    Trucos udyat aplicados: IP directa (1), SNI+Host (2), UA (3),
    TLS permisivo (4) y HTTP/1.1 (5). Devuelve el socket o None.
    """
    for ip in (UDYAT_IP, UDYAT_IP2):
        try:
            raw = _socket.create_connection((ip, 443), timeout=timeout)
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE      # cert self-signed de la IP
            tls = ctx.wrap_socket(raw, server_hostname=TODUS_HOST)
            tls.sendall(_http_get_request(path, range_header, TODUS_HOST))
            tls.settimeout(30)
            return tls
        except Exception as e:
            print(f"  [UDYAT] {ip} falló: {e}", file=sys.stderr, flush=True)
    return None

def open_direct_conn(path, range_header=None, timeout=10):
    """Fallback: TLS con DNS normal del sistema (gasta megas, pero funciona)."""
    try:
        raw = _socket.create_connection((TODUS_HOST, 443), timeout=timeout)
        ctx = ssl.create_default_context()       # cert oficial es válido
        tls = ctx.wrap_socket(raw, server_hostname=TODUS_HOST)
        tls.sendall(_http_get_request(path, range_header, TODUS_HOST))
        tls.settimeout(30)
        return tls
    except Exception as e:
        print(f"  [S3 directo] falló: {e}", file=sys.stderr, flush=True)
        return None

def s3_reachable(timeout=8):
    """HEAD barato para /api/health: ¿S3 responde?"""
    code = subprocess.run(
        ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "-m", str(timeout),
         f"{BASE}?list-type=2&max-keys=1"],
        capture_output=True, text=True).stdout.strip()
    return code

def key_head(key):
    r = subprocess.run(
        ["curl", "-sSI", "-m", "10", f"{S3S}/{quote(key, safe='/')}"],
        capture_output=True, text=True)
    code, size, mtime = None, None, None
    for line in r.stdout.splitlines():
        if line.startswith("HTTP"):   code = line.split()[1]
        if line.lower().startswith("content-length:"): size = int(line.split(":", 1)[1].strip())
        if line.lower().startswith("last-modified:"):   mtime = line.split(":", 1)[1].strip()
    return code, size, mtime

def key_delete(key):
    for _ in range(3):
        r = subprocess.run(
            ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}",
             "-X", "DELETE", f"{S3S}/{quote(key, safe='/')}"],
            capture_output=True, text=True)
        if r.stdout.strip() in ("204", "200", "404"):
            return True
    return False

def hsize(n):
    if not n: return "?"
    if n >= 1024**3: return f"{n/1024**3:.1f} GB"
    if n >= 1024**2: return f"{n/1024**2:.0f} MB"
    if n >= 1024:    return f"{n/1024:.0f} KB"
    return f"{n} B"

# ─── HTML ─────────────────────────────────────────────────────────────────────
def nav_links(path):
    parts = path.strip("/").split("/")
    crumbs = []
    cur = ""
    for p in parts:
        cur += p + "/"
        crumbs.append((p + "/", cur.rstrip("/")))
    html = '<a href="/browse/"><b>root</b></a>'
    for name, href in crumbs:
        html += f' <span style="color:#555">›</span> <a href="/browse/{quote(href)}">{name}</a>'
    return html

VIDEO_CSS = """
  .video-wrap {background:#000;padding:16px 0;border-radius:8px;margin:12px 0}
  .video-wrap video {width:100%;max-width:960px;display:block;margin:0 auto}
"""

def page_header(path, title=""):
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ToDus S3 — {title or path or 'root'}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:monospace;background:#0d1117;color:#e6edf3;min-height:100vh}}
  header{{background:#161b22;border-bottom:1px solid #30363d;padding:14px 20px;
         display:flex;justify-content:space-between;align-items:center}}
  header h1{{color:#58a6ff;font-size:1rem}}
  .info{{color:#8b949e;font-size:0.8rem}}
  .container{{max-width:1100px;margin:0 auto;padding:16px}}
  .pathbar{{background:#161b22;border-bottom:1px solid #30363d;padding:10px 20px;font-size:0.9rem}}
  .actions-bar{{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center}}
  .actions-bar .hint{{color:#8b949e;font-size:0.8rem;margin-left:auto}}
  table{{width:100%;border-collapse:collapse;font-size:0.9rem}}
  th{{text-align:left;padding:8px 12px;background:#161b22;color:#8b949e;
      border-bottom:1px solid #30363d;font-size:0.72rem;text-transform:uppercase}}
  td{{padding:8px 12px;border-bottom:1px solid #21262d;vertical-align:middle}}
  tr:hover{{background:#1f2937}}
  tr.folder{{color:#58a6ff}}
  .size{{color:#8b949e;text-align:right;white-space:nowrap}}
  .mtime{{color:#6e7681;font-size:0.78rem;white-space:nowrap}}
  .name{{max-width:450px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
  .btn{{display:inline-flex;align-items:center;gap:3px;padding:4px 9px;border-radius:6px;
        border:1px solid #30363d;font-size:0.78rem;cursor:pointer;text-decoration:none;
        transition:all .15s;color:#e6edf3;background:#21262d}}
  .btn:hover{{background:#30363d}}
  .btn.copy{{color:#3fb950;border-color:#238636}}
  .btn.copy:hover{{background:#23863633}}
  .btn.del{{color:#f85149;border-color:#da3633}}
  .btn.del:hover{{background:#da363333}}
  .btn.play{{color:#d2a8ff;border-color:#8b5cf6}}
  .btn.play:hover{{background:#8b5cf622}}
  .btn.refresh{{color:#d29922;border-color:#9e6a03}}
  .btn.refresh:hover{{background:#9e6a0322}}
  .btn.back{{color:#79c0ff;border-color:#388bfd}}
  .btn.back:hover{{background:#388bfd22}}
  .empty{{text-align:center;padding:60px;color:#6e7681}}
  .count{{color:#8b949e;font-size:0.82rem;margin-bottom:10px}}
  .flash{{padding:10px 16px;border-radius:6px;margin-bottom:12px;font-size:0.85rem}}
  .flash.ok{{background:#23863622;color:#3fb950;border:1px solid #238636}}
  .flash.err{{background:#da363322;color:#f85149;border:1px solid:#da3633}}
  @media(max-width:600px){{.mtime,.size{{display:none}}.name{{max-width:180px}}}}
{VIDEO_CSS}
</style>
</head>
<body>
<header>
  <h1>📦 ToDus S3 Browser</h1>
  <span class="info">{S3S}</span>
</header>
<div class="pathbar">{nav_links(path)}</div>
<div class="container">
"""

def page_footer():
    return """
<script>
async function copy(url) {
  try {
    await navigator.clipboard.writeText(url);
    document.querySelectorAll('.btn.copy').forEach(b => {
      if (b.textContent.includes('Copiar')) {
        const orig = b.textContent;
        b.textContent = '✅ Copiado';
        setTimeout(() => b.textContent = orig, 1500);
      }
    });
  } catch(e) { prompt('Copia este enlace:', url); }
}
function showFlash(msg, cls) {
  const d = document.createElement('div');
  d.className = 'flash ' + cls; d.textContent = msg;
  document.querySelector('.container').prepend(d);
  setTimeout(() => d.remove(), 3000);
}
</script>
</body></html>"""

def make_row(typ, name, full_key, size, mtime, url):
    icon = "📁" if typ == "folder" else "📄"
    cls  = "folder" if typ == "folder" else ""
    sz   = hsize(size) if size else ("—" if typ == "folder" else "?")
    mt   = mtime[:10] if mtime else ""

    if typ == "folder":
        return (f'<tr class="{cls}">'
                f'<td><a href="/browse/{quote(full_key)}">{icon} {name}/</a></td>'
                f'<td class="size">{sz}</td><td class="mtime">{mt}</td><td></td></tr>')

    video_btn = ""
    if is_video(full_key):
        video_btn = f'<a href="/watch/{quote(full_key)}" class="btn play">▶ Ver</a> '
    copy_btn = f'<button class="btn copy" onclick="copy(\'{url}\')">🔗 Copiar</button>'
    del_btn  = (f'<form class="delete-form" method="get" action="/confirm_delete" style="display:inline">'
                f'<input type="hidden" name="key" value="{quote(full_key)}">'
                f'<button class="btn del" type="submit">🗑️</button></form>')
    return (f'<tr><td><span class="name" title="{name}">{icon} {name}</span></td>'
            f'<td class="size">{sz}</td><td class="mtime">{mt}</td>'
            f'<td style="white-space:nowrap">{video_btn}{copy_btn} {del_btn}</td></tr>')

def build_page(path, flash_msg="", flash_cls=""):
    objs, truncated = list_objects(path)
    subfolders, files = {}, []
    for o in objs:
        rest = o["key"][len(path):].lstrip("/")
        parts = rest.split("/", 1)
        if len(parts) > 1 and parts[0]:
            subfolders[parts[0] + "/"] = subfolders.get(parts[0] + "/", 0) + 1
        elif rest:
            files.append(o)

    flash = f'<div class="flash {flash_cls}">{flash_msg}</div>' if flash_msg else ""
    total = len(files) + len(subfolders)
    parent = "/".join(path.rstrip("/").split("/")[:-1])
    parent = parent + "/" if parent else ""

    html = page_header(path)
    html += f'<div class="count">{total} objetos{" (truncado)" if truncated else ""}</div>'
    html += '<div class="actions-bar">'
    html += f'<a href="/browse/" class="btn refresh">🔄 Actualizar</a>'
    if path:
        html += f'<a href="/browse/{quote(parent)}" class="btn back">← Atras</a>'
    html += '<span class="hint">▶ Ver video · 🔗 Copiar · 🗑️ Eliminar</span>'
    html += '</div>' + flash

    if not objs:
        html += '<div class="empty">Carpeta vacía</div>'
    else:
        html += ('<table><thead><tr><th>Nombre</th><th class="size">Tamaño</th>'
                 '<th class="mtime">Fecha</th><th>Acciones</th></tr></thead><tbody>')
        for sf in sorted(subfolders):
            sf_key = path + sf
            html += make_row("folder", sf.rstrip("/"), sf_key, subfolders[sf], "", "")
        for o in sorted(files, key=lambda x: x["key"]):
            fname = o["key"].split("/")[-1]
            # tamaño y fecha vienen gratis del listing (sin HEAD extra)
            html += make_row("file", fname, o["key"], o["size"], o["mtime"], f"{S3S}/{quote(o['key'])}")
        html += '</tbody></table>'

    html += page_footer()
    return html.encode("utf-8")

# ─── HTTP Handler ─────────────────────────────────────────────────────────────
class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print(f"  {self.client_address[0]} — {fmt % args}")

    def send_html(self, body, code=200):
        try:
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(body))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # navegador cerró la pestaña, inofensivo

    def log_req(self, msg, ip=None):
        who = ip or self.client_address[0] if hasattr(self, "client_address") else "?"
        print(f"  [{who}] {msg}", file=sys.stderr, flush=True)

    def send_json(self, body, code=200):
        """Respuesta JSON con CORS abierto (para la app S3-TV y otros clientes)."""
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", len(body))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    # ── Video streaming proxy (socket TLS directo, udyat + fallback) ─────────
    def stream_s3(self, key):
        """Streamea el objeto de S3 al cliente usando el sistema UDYAT.

        Trucos udyat (replicados con socket TLS, sin curl):
          1. Conexión directa a la IP gratuita (sin DNS público)
          2. SNI + Host: s3.todus.cu
          3. User-Agent: Wget/1.21.3
          4. TLS permisivo (cert self-signed de la IP gratuita)
          5. HTTP/1.1

        Si la IP udyat no responde (WiFi / fuera de Cuba / Render), hace
        fallback a conexión directa con DNS normal (gasta megas pero funciona).
        El body se streamea por chunks — nunca se carga el video en RAM.
        """
        path = f"/stream/{quote(key)}"
        rh = self.headers.get("Range")

        tls = open_udyat_conn(path, rh)
        mode, via = "NO_MEGAS", f"[UDYAT → {UDYAT_IP}]"
        if tls is None:
            tls = open_direct_conn(path, rh)
            mode, via = "DIRECTO", "[S3 directo]"
        if tls is None:
            print(f"  {via} ❌ {key[:55]} → S3 inalcanzable", file=sys.stderr, flush=True)
            self.send_html(b"<h1>502 Bad Gateway</h1>", 502)
            return

        try:
            # Leer headers de la respuesta S3 (hasta doble CRLF, cap 64 KB)
            buf = b""
            while b"\r\n\r\n" not in buf and len(buf) < 65536:
                chunk = tls.recv(8192)
                if not chunk:
                    break
                buf += chunk
            sep = buf.find(b"\r\n\r\n")
            if sep < 0:
                self.send_html(b"<h1>502 Bad Gateway</h1>", 502)
                return
            hdr_raw = buf[:sep].decode("utf-8", "replace")
            first_body = buf[sep + 4:]

            status, s3h = 200, {}
            for line in hdr_raw.split("\r\n"):
                if line.startswith("HTTP"):
                    try: status = int(line.split()[1])
                    except (IndexError, ValueError): pass
                elif ":" in line:
                    k, v = line.split(":", 1)
                    s3h[k.strip().lower()] = v.strip()

            ct = mime_for_key(key)
            cl = s3h.get("content-length")
            cr = s3h.get("content-range", "")

            # UNA sola respuesta (antes se enviaba la status line dos veces)
            self.send_response(status)
            self.send_header("Content-Type", ct)
            if cl: self.send_header("Content-Length", cl)
            self.send_header("Accept-Ranges", "bytes")
            if cr: self.send_header("Content-Range", cr)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            sent = 0
            if first_body:
                self.wfile.write(first_body)
                sent += len(first_body)
            while True:
                chunk = tls.recv(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
                sent += len(chunk)
            rng = f" Range={rh}" if rh else ""
            print(f"  {via} ✅ {key[:55]}{rng} → {sent} bytes ({mode})", file=sys.stderr, flush=True)
        except (BrokenPipeError, ConnectionResetError):
            pass  # cliente cerró la conexión, inofensivo
        except Exception as e:
            print(f"  {via} ❌ {key[:55]} → {e}", file=sys.stderr, flush=True)
        finally:
            try: tls.close()
            except Exception: pass

    # ── GET routes ───────────────────────────────────────────────────────────
    def do_GET(self):
        path = self.path

        # Raíz → lista buckets
        if path in ("/", "/index.html", "/browse"):
            self.send_html(build_page(""))
            return

        # ── API JSON para la app S3-TV ────────────────────────────────────────
        if path.startswith("/api/health"):
            import time as _time
            code = s3_reachable()
            self.send_json(json.dumps({
                "ok": True,
                "service": "todus-explorer",
                "s3_status": code,
                "s3_reachable": code in ("200", "206"),
                "udyat_ip": UDYAT_IP,
                "time": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
            }, ensure_ascii=False).encode())
            return

        if path.startswith("/api/list"):
            from urllib.parse import parse_qs, urlparse
            qs = parse_qs(urlparse(path).query)
            prefix = qs.get("prefix", [""])[0]
            if prefix and not prefix.endswith("/"):
                prefix += "/"
            try:
                limit = min(int(qs.get("limit", ["2000"])[0]), 5000)
            except ValueError:
                limit = 2000
            try:
                objs, truncated = list_objects(prefix, max_objects=limit)
            except Exception as e:
                self.send_json(json.dumps({"error": str(e)}).encode(), 502)
                return
            folders, files = {}, []
            for o in objs:
                rest = o["key"][len(prefix):]
                if "/" in rest:
                    name = rest.split("/", 1)[0]
                    if name:
                        folders[name] = folders.get(name, 0) + 1
                elif rest:
                    files.append(o)
            data = {
                "prefix": prefix,
                "folders": [{"name": n, "key": prefix + n + "/", "count": c}
                            for n, c in sorted(folders.items())],
                "files": [{"name": o["key"].split("/")[-1], "key": o["key"],
                           "size": o["size"], "mtime": (o["mtime"] or "")[:10],
                           "is_video": is_video(o["key"])}
                          for o in sorted(files, key=lambda x: x["key"])],
                "total": len(folders) + len(files),
                "truncated": truncated,
            }
            self.send_json(json.dumps(data, ensure_ascii=False).encode())
            return

        # Stream de video (forza content-type)
        if path.startswith("/play/"):
            key = urllib.parse.unquote(path[6:])
            self.stream_s3(key)
            return

        # Página del reproductor
        if path.startswith("/watch/"):
            key = urllib.parse.unquote(path[7:])
            fname = key.split("/")[-1]
            _, size, mtime = key_head(key)
            ct = mime_for_key(key)
            sz = hsize(size) if size else "?"
            mt = mtime[:10] if mtime else ""
            play_url = f"/play/{quote(key)}"  # proxy udyat (no-megas)
            folder_key = "/".join(key.split("/")[:-1]) + "/"
            w = (page_header("", f"▶ {fname}")
                 + f'<div class="count">{ct} · {sz} · sub: {mt}</div>'
                 + f'<div class="video-wrap">'
                 + f'<video controls autoplay style="width:100%;max-width:960px;display:block;margin:0 auto"'
                 + f' src="{play_url}" type="{ct}"></video>'
                 + '</div>'
                 + f'<a href="/browse/{quote(folder_key)}" class="btn back">← Atras</a>'
                 + page_footer())
            self.send_html(w.encode("utf-8"))
            return

        # Carpeta
        if path.startswith("/browse/"):
            folder = urllib.parse.unquote(path[8:])
            if folder and not folder.endswith("/"): folder += "/"
            self.send_html(build_page(folder))
            return

        # Confirmar eliminación
        if path.startswith("/confirm_delete"):
            from urllib.parse import parse_qs, urlparse
            qs = parse_qs(urlparse(path).query)
            key = qs.get("key", [""])[0]
            if not key:
                self.send_html(build_page("", "Key inválido", "err"))
                return
            fname = key.split("/")[-1]
            folder_key = "/".join(key.split("/")[:-1]) + "/"
            c = (page_header("", f"Confirmar: {fname}")
                 + f'<div class="flash err" style="font-size:1rem">'
                 + f'¿Eliminar <b>{fname}</b>?</div>'
                 + '<form method="post" action="/delete" style="display:inline">'
                 + f'<input type="hidden" name="key" value="{quote(key)}">'
                 + '<button class="btn del" type="submit" style="font-size:1rem;padding:8px 20px">🗑️ Sí, eliminar</button>'
                 + '</form>'
                 + f'<a href="/browse/{quote(folder_key)}" class="btn" style="margin-left:10px">Cancelar</a>'
                 + page_footer())
            self.send_html(c.encode("utf-8"))
            return

        self.send_html(b"<h1>404 Not Found</h1>", 404)

    # ── POST routes ──────────────────────────────────────────────────────────
    def do_POST(self):
        from urllib.parse import parse_qs, unquote
        cl = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(cl).decode()
        data = parse_qs(body)

        if self.path == "/delete":
            key = unquote(data.get("key", [""])[0])
            ok = key_delete(key)
            folder = "/".join(key.split("/")[:-1])
            folder = folder + "/" if folder else ""
            self.send_html(build_page(folder,
                                      "✅ Eliminado" if ok else "❌ Error",
                                      "ok" if ok else "err"))
        else:
            self.send_html(b"<h1>405 Method Not Allowed</h1>", 405)

# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import threading, webbrowser

    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    srv = ReusableTCPServer((HOST, PORT), Handler)
    url = f"http://localhost:{PORT}"

    # Ignore SIGTERM (Render lo usa para detener) → shutdown limpio
    def _ign(sig, frame): pass
    signal.signal(signal.SIGTERM, _ign)

    print(f"""
  ╔══════════════════════════════════════════╗
  ║  🌐 ToDus S3 Browser — puerto {PORT}         ║
  ║  http://localhost:{PORT}
  ║
  ║  ▶ Videos: stream sin gastar megas       ║
  ║  Ctrl+C para detener
  ╚══════════════════════════════════════════╝
""")
    if os.environ.get("RENDER"):
        print("  Corriendo en Render ✅")
    else:
        print(f"  Abre http://localhost:{PORT} en tu navegador")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
