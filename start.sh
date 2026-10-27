#!/bin/bash
# ============================================================
#  ToDus S3 Explorer — iniciar servidor con logs
#  Muestra en tiempo real cada peticion y si usa udyat
# ============================================================
cd "$(dirname "$0")/.."

# Puerto donde escuchara el servidor
PORT=8080
URL="http://localhost:$PORT"

# Limpiar procesos viejos en ese puerto
pkill -f "s3_server.py" 2>/dev/null || true
sleep 1

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║         🚀 ToDus S3 Explorer — iniciando             ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  🌐 URL:  $URL                ║"
echo "║  📱 Abre esa direccion en tu navegador               ║"
echo "║                                                      ║"
echo "║  Los LOGS debajo mostraran cada peticion.            ║"
echo "║  Busca [UDYAT] para confirmar que NO gasta MB.       ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "--- Logs (Ctrl+C para detener) ---"
echo ""

# Iniciar con logs en stderr (el servidor ya escribe a stderr)
python3 scripts/s3_server.py 2>&1
