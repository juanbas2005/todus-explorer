# Instalación

## 1. Instalar Termux (Android)

Descarga **Termux** desde F-Droid (no desde Google Play, la versión vieja está rota).

```
https://f-droid.org/packages/com.termux/
```

## 2. Configurar Termux

```bash
# Actualizar paquetes
pkg update && pkg upgrade -y

# Instalar Python y curl
pkg install python -y
```

## 3. Descargar el proyecto

```bash
cd ~
git clone https://github.com/juanbas2005/todus-explorer.git
cd todus-explorer
```

O si ya tienes los archivos, copia la carpeta `scripts/`, `examples/` y `udyat/` a tu teléfono.

## 4. Probar que funciona

```bash
# Navegador web (recomendado)
python3 scripts/s3_server.py
# Se abre automáticamente http://localhost:8080

# Navegador CLI
python3 scripts/s3_browser.py
```

## 5. Permisos de red

En Termux, los scripts ya tienen acceso a red por defecto. No necesitas `INTERNET` permission como en apps normales.

## 6. (Opcional) Barra de progreso con pv

```bash
pkg install coreutils   # para numfmt
# pv ya viene con algunos builds de Termux
# Si no: pkg install pv
```

## 7. (Opcional) Subir archivos

```bash
pkg install python -y
pip install requests
chmod +x examples/curl_with_retry.sh
```

## Solución de problemas

### "Address already in use"
Otro proceso está usando el puerto 8080. Mátalo:

```bash
fuser -k 8080/tcp
python3 scripts/s3_server.py
```

### Puerto ocupado con puerto diferente
```bash
PORT=9090 python3 scripts/s3_server.py
```

### curl no encontrado
```bash
pkg install curl
```

### El video no reproduce
Verifica que estés en **datos móviles de ETECSA** (no WiFi). La IP `152.207.206.86` es zero-rated solo en la red móvil.
