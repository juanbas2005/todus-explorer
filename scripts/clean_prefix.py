#!/usr/bin/env python3
"""Borra todos los objetos de un prefijo en s3.todus.cu/stream.

Uso:
  python clean_prefix.py                 # interactivo
  python clean_prefix.py <prefijo> [...]  # directo (pide confirmación igual)
  python clean_prefix.py --yes <prefijo>  # directo sin confirmación
"""
import subprocess, sys, urllib.parse, xml.etree.ElementTree as ET, time
from urllib.parse import quote

BASE = "https://s3.todus.cu/stream"
NS = "http://s3.amazonaws.com/doc/2006-03-01/"
TIMEOUT = 60


def curl(url):
    r = subprocess.run(["curl", "-sS", "-m", str(TIMEOUT), url],
                       capture_output=True, text=True)
    return r.stdout


def list_keys(prefix):
    marker, keys = "", []
    enc = quote(prefix, safe="")
    while True:
        url = f"{BASE}?list-type=2&prefix={enc}&continuation-token={quote(marker)}&max-keys=1000" if marker \
              else f"{BASE}?list-type=2&prefix={enc}&max-keys=1000"
        page = curl(url)
        root = ET.fromstring(page)
        for c in root.findall(f"{{{NS}}}Contents"):
            keys.append(c.find(f"{{{NS}}}Key").text)
        trunc = root.find(f"{{{NS}}}IsTruncated")
        next_t = root.find(f"{{{NS}}}NextContinuationToken")
        if trunc is not None and trunc.text == "true" and next_t is not None and next_t.text:
            marker = next_t.text
        else:
            break
    return keys


def delete(key):
    url = f"{BASE}/{quote(key, safe='/')}"
    for attempt in range(1, 4):
        r = subprocess.run(["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}",
                           "-X", "DELETE", url],
                          capture_output=True, text=True)
        code = r.stdout.strip()
        if code in ("204", "200", "404"):
            return True
        time.sleep(2)
    return False


def run(prefix, confirm=True):
    prefix = prefix.rstrip("/")
    keys = list_keys(prefix)
    print(f"[{prefix}] {len(keys)} objetos:")
    for k in keys[:10]:
        print(f"  {k}")
    if len(keys) > 10:
        print(f"  ... y {len(keys) - 10} más")
    if not keys:
        print("  Nada que borrar.")
        return

    if confirm:
        resp = input(f"Borrar {len(keys)} objetos de '{prefix}'? [s/N] > ").strip().lower()
        if resp not in ("s", "si"):
            print("Cancelado.")
            return

    fails = 0
    for k in keys:
        ok = delete(k)
        print(f"  204 {k}" if ok else f"  FAIL {k}")
        if not ok:
            fails += 1
    print(f"[{prefix}] Listo: {len(keys)} procesados, {fails} fallos.")


def banner():
    for p in ("users", "dk"):
        enc = quote(p, safe="")
        page = curl(f"{BASE}?list-type=2&prefix={enc}&max-keys=1")
        try:
            root = ET.fromstring(page)
            n = root.find(f"{{{NS}}}KeyCount")
            print(f"  {p}/ -> {n.text if n is not None else '?'} objetos")
        except Exception:
            print(f"  {p}/ -> ? objetos")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--yes" in args:
        args.remove("--yes")
        confirm = False
    else:
        confirm = True

    if args:
        for p in args:
            run(p, confirm=confirm)
    else:
        print("=== ToDus S3 cleaner ===")
        banner()
        while True:
            p = input("\nPrefijo a borrar (enter para salir) > ").strip()
            if not p:
                break
            run(p, confirm=confirm)
        print("Saliendo.")
