#!/data/data/com.termux/files/usr/bin/env bash
# ============================================================
# udyat-test.sh — Prueba del sistema UDYAT para s3.todus.cu
# ============================================================
# Replica en bash los 5 trucos del sistema UDYAT:
#   1. Resolución directa a la IP gratuita (no DNS público)
#   2. Host header override: Host: s3.todus.cu
#   3. UA spoofing: Wget/1.21.3
#   4. TLS permisivo (--no-check-certificate / --insecure)
#   5. HTTP/1.1 forzado
#
# Uso:
#   pkg install curl pv      # pv es opcional (barra estilo pv)
#   chmod +x udyat-test.sh
#   ./udyat-test.sh "<URL_TODUS>"
#
# O sin argumento: modo interactivo — pega la URL cuando lo pida
# (Enter solo usa la URL por defecto).
#
# Nota: en Termux sobre ETECSA móvil, la IP 152.207.206.86 es
# zero-rated (no gasta megas). En WiFi o fuera de Cuba, el script
# sigue funcionando pero la descarga sí cuenta para tu plan.
# ============================================================

# Sin set -e: este es un script interactivo y grep/awk pueden devolver
# exit 1 sin que eso sea un error real (ej. grep sin matches).
# Mantenemos -u (errores en vars no definidas) y -o pipefail solo donde
# haga falta via `set -o pipefail` local.
set -u

# ---- Configuración ----
TODUS_IP="${TODUS_IP:-152.207.206.86}"      # IP gratuita ETECSA
TODUS_HOST="s3.todus.cu"
UA="Wget/1.21.3"                            # UA exacto del sistema UDYAT
OUT_DIR="${OUT_DIR:-./udyat-downloads}"

# URL por defecto (la que pasaste). Cámbiala o pásala como $1.
DEFAULT_URL='https://s3.todus.cu/stream/dk/tg_7970466590/G%20Fatt%20x%20Floke%20Rose%20-%20%E1%80%80%E1%80%BC%E1%80%9A%E1%80%BA%E1%80%90%E1%80%BD%E1%80%B1%E1%80%86%E1%80%AE%E1%80%81%E1%80%9B%E1%80%AE%E1%80%B8%20%28Official%20Lyric%20Video%29%20%5BxwEeM7ap4oY%5D.mp4'

URL="${1:-}"

# Colores para salida bonita
R='\033[1;31m'; G='\033[1;32m'; Y='\033[1;33m'; B='\033[1;36m'; N='\033[0m'

echo -e "${B}╔══════════════════════════════════════════════╗${N}"
echo -e "${B}║   UDYAT-TEST  ·  s3.todus.cu  ·  no-megas    ║${N}"
echo -e "${B}╚══════════════════════════════════════════════╝${N}"
echo

# Modo interactivo: sin argumento, pide la URL (Enter = la de defecto)
if [ -z "$URL" ]; then
    read -r -p $'\033[1;36mPega la URL: \033[0m' URL
fi
URL="${URL:-$DEFAULT_URL}"

echo -e "${Y}URL original:${N} $URL"
echo -e "${Y}IP gratuita:${N}  $TODUS_IP"
echo -e "${Y}Host header:${N}  $TODUS_HOST"
echo -e "${Y}User-Agent:${N}  $UA"
echo

mkdir -p "$OUT_DIR"

# Extrae el path de la URL (todo después del host)
# https://s3.todus.cu/stream/abc.mp4?x=1  ->  /stream/abc.mp4?x=1
PATH_URL="${URL#https://$TODUS_HOST}"
PATH_URL="${PATH_URL#http://$TODUS_HOST}"

# ----------------------------------------------------------
# PASO 1: Pre-flight check (HEAD 3s a la IP gratuita por HTTPS)
# ----------------------------------------------------------
# El server ToDus acepta HTTPS en la IP gratuita (con cert self-signed).
# Por eso usamos --insecure + SNI/Host override.
echo -e "${B}[1/4]${N} Pre-flight check a https://$TODUS_IP/ ..."
if curl -s -o /dev/null -w "HTTP %{http_code}" \
        --max-time 3 \
        --insecure \
        --resolve "$TODUS_HOST:443:$TODUS_IP" \
        -H "Host: $TODUS_HOST" \
        -A "$UA" \
        --head \
        "https://$TODUS_HOST/" 2>/dev/null | grep -q "HTTP"; then
    echo -e "${G}    ✓ IP gratuita responde por HTTPS${N}"
    MODE="NO_MEGAS"
else
    echo -e "${R}    ✗ IP gratuita no responde — fallback a HTTPS directo (DNS del sistema)${N}"
    MODE="FALLBACK_HTTPS"
fi
echo

# ----------------------------------------------------------
# PASO 2: Probe (descubre tamaño + soporte de rangos)
# ----------------------------------------------------------
echo -e "${B}[2/4]${N} Probe Range bytes=0-0 ..."

# Construye los args comunes de curl
CURL_COMMON=(
    --max-time 15
    --insecure
    --http1.1
    -H "Host: $TODUS_HOST"
    -H "Range: bytes=0-0"
    -H "Accept-Encoding: identity"
    -H "Accept: */*"
    -H "Connection: keep-alive"
    -A "$UA"
    -s
    -D -
    -o /dev/null
)

if [ "$MODE" = "NO_MEGAS" ]; then
    # Forzamos que curl resuelva s3.todus.cu a la IP gratuita
    PROBE_OUTPUT=$(curl "${CURL_COMMON[@]}" \
        --resolve "$TODUS_HOST:443:$TODUS_IP" \
        "https://$TODUS_HOST$PATH_URL" 2>/dev/null || true)
else
    # Fallback: HTTPS directo, dejamos que el OS resuelva
    PROBE_OUTPUT=$(curl "${CURL_COMMON[@]}" \
        "https://$TODUS_HOST$PATH_URL" 2>/dev/null || true)
fi

echo "$PROBE_OUTPUT" | grep -iE "^(HTTP|Content-Range|Content-Length|Accept-Ranges|ETag|Location):" | sed 's/^/    /'

# Sigue redirects 301/302 si los hay (ToDus a veces redirige HTTP→HTTPS)
# Nota: grep devuelve exit 1 si no hay match, lo que rompería set -e.
LOCATION=$(echo "$PROBE_OUTPUT" | grep -i "^Location:" | awk '{print $2}' | tr -d '\r' || true)
if [ -n "$LOCATION" ]; then
    echo -e "${Y}    → Redirect detectado, siguiendo a: $LOCATION${N}"
    if [ "$MODE" = "NO_MEGAS" ]; then
        PROBE_OUTPUT=$(curl "${CURL_COMMON[@]}" \
            --resolve "$TODUS_HOST:443:$TODUS_IP" \
            "$LOCATION" 2>/dev/null || true)
    else
        PROBE_OUTPUT=$(curl "${CURL_COMMON[@]}" \
            "$LOCATION" 2>/dev/null || true)
    fi
    echo "$PROBE_OUTPUT" | grep -iE "^(HTTP|Content-Range|Content-Length|Accept-Ranges):" | sed 's/^/    /'
fi

# Tamaño: primero Content-Range (más confiable en ToDus), luego Content-Length
TOTAL_SIZE=$(echo "$PROBE_OUTPUT" | grep -i "^Content-Range:" | sed -n 's#^.*/\([0-9]\+\).*#\1#p' | tr -d '\r' || true)
if [ -z "$TOTAL_SIZE" ]; then
    TOTAL_SIZE=$(echo "$PROBE_OUTPUT" | grep -i "^Content-Length:" | awk '{print $2}' | tr -d '\r' || true)
fi

if [ -z "$TOTAL_SIZE" ] || [ "$TOTAL_SIZE" = "0" ]; then
    echo -e "${R}    ✗ No se pudo determinar el tamaño del archivo${N}"
    echo -e "${Y}    El server puede estar caído o la URL es inválida${N}"
    exit 1
fi
HUMAN_SIZE=$(numfmt --to=iec --suffix=B "$TOTAL_SIZE" 2>/dev/null || echo "${TOTAL_SIZE}B")
echo -e "${G}    ✓ Tamaño total: $HUMAN_SIZE ($TOTAL_SIZE bytes)${N}"
echo

# ----------------------------------------------------------
# PASO 3: Descarga con curl | pv (mismos trucos UDYAT, barra estilo pv)
# ----------------------------------------------------------
# Filename: último segmento del path, URL-decoded
FILENAME=$(echo "$PATH_URL" | sed 's/?.*//' | awk -F/ '{print $NF}' | python3 -c "import sys,urllib.parse;print(urllib.parse.unquote(sys.stdin.read().strip()))" 2>/dev/null || echo "download.bin")
OUT_FILE="$OUT_DIR/$FILENAME"

echo -e "${B}[3/4]${N} Descargando a: $OUT_FILE"
echo -e "${Y}    Modo: $MODE${N}"

# Args comunes de curl — mismos trucos que UDYAT; --resolve manda SNI
# correcto (mejor que el hack del Host header de wget)
CURL_DL=(
    --insecure
    --http1.1
    -A "$UA"
    -H "Accept: */*"
    -H "Accept-Encoding: identity"
    -H "Connection: keep-alive"
    -sS
    --retry 5
    --retry-delay 1
)

if [ "$MODE" = "NO_MEGAS" ]; then
    DOWNLOAD_URL="https://$TODUS_HOST$PATH_URL"
    RESOLVE=(--resolve "$TODUS_HOST:443:$TODUS_IP")
else
    # FALLBACK: HTTPS directo al host (DNS del sistema)
    DOWNLOAD_URL="https://$TODUS_HOST$PATH_URL"
    RESOLVE=()
fi
echo -e "${Y}    URL efectiva: $DOWNLOAD_URL${N}"
echo

# Barra de progreso estilo pv si está instalado Y funciona (algunos
# builds de pv para Android son non-PIE y no corren); si no, el medidor
# nativo de curl (%, bytes, velocidad, ETA).
# ponytail: sin reanudar (-C -) porque por pipe no se puede; --retry 5
# cubre cortes de red.
if echo x | pv >/dev/null 2>&1; then
    curl "${CURL_DL[@]}" -sS "${RESOLVE[@]}" "$DOWNLOAD_URL" \
        | pv -s "$TOTAL_SIZE" -N "descarga" > "$OUT_FILE"
else
    curl "${CURL_DL[@]}" -o "$OUT_FILE" "${RESOLVE[@]}" "$DOWNLOAD_URL"
fi

echo
echo -e "${G}    ✓ Descarga completada: $OUT_FILE${N}"

# ----------------------------------------------------------
# PASO 4: Verificación MD5 (como hace el sistema UDYAT)
# ----------------------------------------------------------
echo -e "${B}[4/4]${N} Verificando integridad..."
ACTUAL_SIZE=$(stat -c %s "$OUT_FILE" 2>/dev/null || stat -f %z "$OUT_FILE")
ACTUAL_MD5=$(md5sum "$OUT_FILE" 2>/dev/null | awk '{print $1}' || md5 "$OUT_FILE" 2>/dev/null | awk '{print $NF}')

echo -e "${Y}    Tamaño esperado:${N}  $TOTAL_SIZE bytes ($HUMAN_SIZE)"
echo -e "${Y}    Tamaño descargado:${N} $ACTUAL_SIZE bytes"
echo -e "${Y}    MD5:${N} $ACTUAL_MD5"

if [ "$ACTUAL_SIZE" = "$TOTAL_SIZE" ]; then
    echo -e "${G}    ✓ Tamaño correcto — descarga íntegra${N}"
else
    echo -e "${R}    ✗ Tamaño incorrecto — descarga incompleta o corrupta${N}"
    exit 1
fi

echo
echo -e "${G}╔══════════════════════════════════════════════╗${N}"
echo -e "${G}║  ✓ DESCARGA COMPLETADA — modo $MODE          ║${N}"
echo -e "${G}╚══════════════════════════════════════════════╝${N}"
echo
echo -e "Archivo: ${B}$OUT_FILE${N}"
echo
if [ "$MODE" = "NO_MEGAS" ]; then
    echo -e "${G}Si estás en ETECSA móvil, esta descarga NO gastó megas${N}"
    echo -e "${G}porque fue por la IP gratuita $TODUS_IP (zero-rated).${N}"
else
    echo -e "${Y}⚠ Esta descarga fue por HTTPS directo y PUEDE haber gastado megas${N}"
    echo -e "${Y}  La IP gratuita no respondió al pre-flight check.${N}"
fi
