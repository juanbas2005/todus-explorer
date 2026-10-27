#!/usr/bin/env python3
"""Navegador y cleaner interactivo del bucket s3.todus.cu/stream

Uso:
  python s3_browser.py               # interactivo
  python s3_browser.py --delete-all  # borra todo sin preguntar
"""
import subprocess, sys, xml.etree.ElementTree as ET
from urllib.parse import quote

BASE = "https://s3.todus.cu/stream"
NS = "http://s3.amazonaws.com/doc/2006-03-01/"
TIMEOUT = 60


def curl(url):
    r = subprocess.run(["curl", "-sS", "-m", str(TIMEOUT), url],
                       capture_output=True, text=True)
    return r.stdout


def list_keys(prefix="", max_keys=1000):
    """Lista keys bajo un prefijo (paginando si es necesario)."""
    enc = quote(prefix, safe="")
    marker, keys = "", []
    while True:
        url = (f"{BASE}?list-type=2&prefix={enc}"
               f"&continuation-token={quote(marker)}&max-keys={max_keys}") if marker \
               else f"{BASE}?list-type=2&prefix={enc}&max-keys={max_keys}"
        page = curl(url)
        root = ET.fromstring(page)
        for c in root.findall(f"{{{NS}}}Contents"):
            keys.append(c.find(f"{{{NS}}}Key").text)
        trunc = root.find(f"{{{NS}}}IsTruncated")
        nxt = root.find(f"{{{NS}}}NextContinuationToken")
        if trunc is not None and trunc.text == "true" and nxt is not None and nxt.text:
            marker = nxt.text
        else:
            break
    return keys


def key_info(key):
    """Devuelve (size_bytes, last_modified) para un key."""
    enc = quote(key, safe="/")
    page = curl(f"{BASE}?list-type=2&prefix=&max-keys=1")
    # mejor con HEAD directo
    r = subprocess.run(["curl", "-sSI", "-m", "10",
                        f"{BASE}/{enc}"], capture_output=True, text=True)
    out = r.stdout
    size = modified = None
    for line in out.splitlines():
        if line.lower().startswith("content-length:"):
            size = int(line.split(":")[1].strip())
        if line.lower().startswith("last-modified:"):
            modified = line.split(":", 1)[1].strip()
    return size, modified


def human_size(n):
    if n is None: return "?"
    if n >= 1024**3: return f"{n/1024**3:.1f} GB"
    if n >= 1024**2: return f"{n/1024**2:.0f} MB"
    if n >= 1024:    return f"{n/1024:.0f} KB"
    return f"{n} B"


def head(key):
    r = subprocess.run(["curl", "-sSI", "-m", "10",
                        f"{BASE}/{quote(key, safe='/')}"],
                       capture_output=True, text=True)
    out = r.stdout
    code = None
    for line in out.splitlines():
        if line.startswith("HTTP"):
            code = line.split()[1]
    size = modified = None
    for line in out.splitlines():
        if line.lower().startswith("content-length:"):
            size = int(line.split(":")[1].strip())
        if line.lower().startswith("last-modified:"):
            modified = line.split(":", 1)[1].strip()
    return code, size, modified


def delete(key):
    for attempt in range(1, 4):
        r = subprocess.run(["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}",
                            "-X", "DELETE",
                            f"{BASE}/{quote(key, safe='/')}"],
                           capture_output=True, text=True)
        if r.stdout.strip() in ("204", "200", "404"):
            return True
    return False


def fmt_key(key, show_prefix_len=0):
    """Muestra key truncado a ancho de terminal."""
    name = key.split("/")[-1]
    prefix = "/".join(key.split("/")[:-1])
    return key, name, prefix


def browse_folder(prefix, parent_prefix=""):
    """Navega una carpeta, devuelve la acción elegida (back / delete / quit)."""
    keys = list_keys(prefix)
    if not keys:
        print("  (vacía)")
        return None

    # Determina sub-carpetas únicas y archivos
    subfolders = {}
    files = []
    for k in keys:
        parts = k[len(prefix):].lstrip("/").split("/")
        if len(parts) > 1 and parts[0]:
            subfolders[parts[0]] = subfolders.get(parts[0], 0) + 1
        else:
            files.append(k)

    # Encabezado
    print(f"\n  [{prefix or '(root)'}]  {len(keys)} objetos")
    print("  " + "-" * 60)

    idx = 0
    items = []
    # Sub-carpetas
    for sf in sorted(subfolders.keys()):
        idx += 1
        items.append(("folder", f"{prefix}{sf}/"))
        print(f"  [{idx:3d}] 📁 {sf}/  ({subfolders[sf]} archivos)")
    # Archivos
    for f in sorted(files):
        idx += 1
        items.append(("file", f))
        fname = f.split("/")[-1]
        print(f"  [{idx:3d}] 📄 {fname}")

    print(f"  [  0] ← Volver")
    print(f"  [999] Eliminar TODOS en esta vista ({len(files)} archivos)")

    sel = input("  > ").strip()
    if sel == "0":
        return None  # volver
    if sel == "999":
        return ("delete_all", [k for _, k in items if _ == "file"])

    try:
        n = int(sel)
        if n < 1 or n > len(items):
            return None
        typ, path = items[n - 1]
        if typ == "folder":
            return ("enter", path)
        else:
            return ("delete_one", path)
    except ValueError:
        return None


def browser_loop():
    """Loop principal de navegación."""
    path = ""

    while True:
        result = browse_folder(path)

        if result is None:
            if path:
                # volver a la carpeta anterior
                path = "/".join(path.rstrip("/").split("/")[:-1])
                if path and not path.endswith("/"):
                    path += "/"
                # asegurar que la carpeta padre tenga prefijo para navegar
                # si estamos en root, salir
                if not path:
                    print("  Saliendo del navegador.")
                    break
            else:
                break

        elif result[0] == "enter":
            path = result[1]

        elif result[0] == "delete_one":
            key = result[1]
            conf = input(f"  Eliminar '{key.split('/')[-1]}'? [s/N] > ").strip().lower()
            if conf in ("s", "si"):
                ok = delete(key)
                print(f"  {'✅ 204' if ok else '❌ FAIL'} {key}")
            else:
                print("  Cancelado.")

        elif result[0] == "delete_all":
            keys = result[1]
            if not keys:
                print("  Nada que borrar.")
                continue
            conf = input(f"  Eliminar {len(keys)} archivos? [s/N] > ").strip().lower()
            if conf not in ("s", "si"):
                print("  Cancelado.")
                continue
            fails = 0
            for k in keys:
                ok = delete(k)
                print(f"  {'✅ 204' if ok else '❌ FAIL'} {k}")
                if not ok:
                    fails += 1
            print(f"  Hecho: {len(keys)} procesos, {fails} fallos.")


def summary():
    """Muestra resumen del bucket."""
    print("\n  === Resumen del bucket ===")
    keys = list_keys("")
    if not keys:
        print("  Bucket vacío.")
        return

    # agrupar por prefijo de nivel 1
    folders = {}
    for k in keys:
        top = k.split("/")[0] + "/"
        folders[top] = folders.get(top, []) + [k]

    total_size = 0
    for folder, klist in sorted(folders.items(), key=lambda x: -len(x[1])):
        print(f"\n  📂 {folder}  ({len(klist)} objetos)")
        # muestra hasta 5 archivos
        for k in klist[:5]:
            print(f"      {k.split('/')[-1]}")
        if len(klist) > 5:
            print(f"      ... y {len(klist)-5} más")
        # tamaño estimado del folder vía HEAD del primer archivo
        if klist:
            _, sz, _ = head(klist[0])
            if sz:
                total_size += sz * len(klist)

    print(f"\n  Total: {len(keys)} objetos")


def delete_all(force=False):
    """Borra todo el bucket sin confirmación."""
    keys = list_keys("")
    if not keys:
        print("  Bucket vacío.")
        return
    print(f"  Eliminando {len(keys)} objetos...")
    fails = 0
    for k in keys:
        ok = delete(k)
        if ok:
            print(f"  204 {k}")
        else:
            print(f"  FAIL {k}")
            fails += 1
    print(f"  Listo: {len(keys)} procesos, {fails} fallos.")


if __name__ == "__main__":
    if "--delete-all" in sys.argv:
        delete_all()
        sys.exit(0)

    print("  === S3 Browser — s3.todus.cu/stream ===")
    print("  1) Resumen del bucket")
    print("  2) Navegar y borrar interactivo")
    print("  3) Borrar todo (con confirmación)")
    print("  4) Listar prefijos")
    opt = input("  > ").strip()

    if opt == "1":
        summary()
    elif opt == "2":
        browser_loop()
    elif opt == "3":
        delete_all()
    elif opt == "4":
        keys = list_keys("")
        folders = sorted(set(k.split("/")[0] for k in keys))
        print(f"  {len(folders)} prefijos de nivel 1:")
        for f in folders:
            n = sum(1 for k in keys if k.startswith(f + "/"))
            print(f"    {f}/  -> {n} objetos")
    else:
        print("  Saliendo.")
