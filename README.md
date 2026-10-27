# ToDus Explorer — Gestor de S3 desde el navegador

Explora, reproduce videos y gestiona el bucket **s3.todus.cu/stream** desde cualquier navegador, sin gastar megas en ETECSA móvil.

```
navegador → s3_server.py (localhost:8080) → S3 via IP udyat
                                              152.207.206.86
                                              (zero-rated, no megas)
```

---

## Quick start

```bash
pkg install python -y
python3 scripts/s3_server.py
# Se abre http://localhost:8080 automáticamente
```

---

## Estructura

```
todus-explorer/
├── README.md                  ← este archivo
├── .gitignore
├── LICENSE
│
├── scripts/
│   ├── s3_server.py           ← servidor web (navegador + videos sin megas)
│   ├── s3_browser.py          ← navegador CLI interactivo
│   └── clean_prefix.py        ← limpia todos los objetos de un prefijo
│
├── examples/
│   ├── python_upload.py       ← subir archivos con requests
│   └── curl_with_retry.sh     ← subir archivos con curl
│
├── udyat/
│   └── udyat-test.sh          ← descarga sin megas (mismo sistema de video)
│
└── docs/
    ├── INSTALL.md             ← guía de instalación completa
    ├── VIDEO_STREAMING.md     ← cómo funciona el streaming
    └── UDYAT_SYSTEM.md        ← cómo funciona zero-rated
```

---

## Scripts disponibles

### 🌐 `s3_server.py` — Servidor web
El más completo. Sirve una interfaz web para navegar archivos, ver videos y copiar/eliminar enlaces.

```bash
python3 scripts/s3_server.py
# Abre http://localhost:8080
```

| Función | Descripción |
|---------|-------------|
| 📁 Navegar | Explora carpetas del bucket |
| ▶ Ver video | Reproduce MP4/MKV/etc en el navegador (sin megas) |
| 🔗 Copiar enlace | Copia la URL directa al portapapeles |
| 🗑️ Eliminar | Borra archivos individuales del bucket |
| 🔄 Actualizar | Recarga la lista actual |

### 🖥️ `s3_browser.py` — Navegador CLI
Interactivo, sin navegador.

```bash
python3 scripts/s3_browser.py
```

### 🧹 `clean_prefix.py` — Limpiador masivo
Borra todos los objetos de un prefijo. Útil para limpiar `users/` que se llena continuamente.

```bash
# Modo interactivo
python3 scripts/clean_prefix.py

# Directo (pide confirmación)
python3 scripts/clean_prefix.py users/

# Sin preguntar
python3 scripts/clean_prefix.py --yes users/
```

### 📤 Subir archivos

```bash
# Con Python
python3 examples/python_upload.py <archivo> [carpeta]

# Con curl
chmod +x examples/curl_with_retry.sh
./examples/curl_with_retry.sh <archivo> [carpeta]
```

### ⬇️ Descarga sin megas (udyat)

```bash
chmod +x udyat/udyat-test.sh
./udyat/udyat-test.sh "<URL_DEL_VIDEO>"
```

---

## Cómo funciona el streaming sin megas

Cuando reproduces un video en `s3_server.py`:

1. El navegador pide `/play/<key>` a tu servidor local
2. El servidor resuelve `s3.todus.cu` → `152.207.206.86` (IP gratuita ETECSA)
3. Descarga el video desde S3 usando esa IP (viaja por la red zero-rated)
4. Devuelve el video al navegador con `Content-Type: video/mp4`

```
navegador → localhost:8080/play/... → 152.207.206.86 (IP udyat) → S3
```

El navegador no accede directamente a `s3.todus.cu`. Todo pasa por el proxy local, que usa la IP zero-rated.

---

## Requisitos

- **Python 3** (viene en Termux: `pkg install python`)
- **curl** (viene en Termux)
- **Android con Termux** (para acceso zero-rated)

WiFi funciona pero sí gasta megas. En datos móviles ETECSA + este sistema = zero megas.

---

## Notas

- Todos los archivos en `s3.todus.cu/stream` son de acceso público (lectura anónima)
- Las escrituras (subida/borrado) requieren las cabeceras de autenticación del bot ToDus
- La IP udyat `152.207.206.86` funciona SOLO desde la red móvil de ETECSA en Cuba
- Fuera de Cuba o en WiFi, el servidor sigue funcionando pero no será zero-rated
