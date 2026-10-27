# Cómo funciona el streaming de video sin megas

## El problema

Cuando subes un video a ToDus S3, queda accesible públicamente:

```
https://s3.todus.cu/stream/users/df/7970466590/video.mp4
```

Pero hay dos problemas:

1. **S3 sirve los videos como `application/octet-stream`**, no como `video/mp4`. El navegador no sabe que es un video y lo descarga en vez de reproducirlo.
2. **Si accedes directo a S3**, gastas megas de tu plan de datos.

## La solución: proxy `/play/`

El servidor `s3_server.py` tiene un endpoint `/play/<key>` que hace de proxy:

```
navegador  →  localhost:8080/play/...  →  152.207.206.86 (IP udyat)  →  S3
```

El proxy hace tres cosas:

### 1. Fuerza `Content-Type: video/mp4`
S3 responde con `application/octet-stream`. El proxy lo convierte a `video/mp4` (o `video/webm`, etc.) según la extensión del archivo. Así el navegador sabe que es un video.

### 2. Soporta Range requests (seek)
El navegador pide `Range: bytes=0-1` para buscar en el video. El proxy reenvía ese header a S3 y devuelve el rango correcto. Sin esto, no puedes hacer seek en el video.

### 3. Usa la IP udyat (no megas)
En vez de resolver `s3.todus.cu` por DNS normal, el proxy fuerza:

```bash
curl --resolve "s3.todus.cu:443:152.207.206.86" \
     -H "Host: s3.todus.cu" \
     -A "Wget/1.21.3" \
     --insecure \
     --http1.1 \
     "https://s3.todus.cu/stream/..."
```

Esto hace que curl se conecte a `152.207.206.86` (la IP zero-rated de ETECSA) en vez del DNS público. El tráfico por esa IP no consume datos móviles.

## Flujo completo

```
1. Usuario abre s3_server.py
   → s3_server.py arranca en localhost:8080

2. Navega a /browse/users/df/7970466590/
   → Lista archivos, detecta .mp4 → muestra botón "▶ Ver"

3. Clic en "▶ Ver" → abre /watch/users/df/.../video.mp4
   → Página HTML con: <video src="/play/...video.mp4" type="video/mp4">

4. Navegador pide /play/...video.mp4 → s3_server.py recibe la petición

5. s3_server.py ejecuta curl con trucos udyat:
   curl --resolve s3.todus.cu:443:152.207.206.86 \
        -H "Host: s3.todus.cu" \
        "https://s3.todus.cu/stream/users/df/.../video.mp4"

6. curl descarga desde S3 por la IP zero-rated

7. s3_server.py recibe bytes → responde al navegador con:
   Content-Type: video/mp4
   Accept-Ranges: bytes

8. Navegador reproduce el video (puede hacer seek porque hay Range support)
```

## Requisitos para zero-rated

- Android con Termux
- SIM de ETECSA (ETECSA móvil, no Nauta)
- Datos móviles ACTIVOS (no WiFi)
- La IP `152.207.206.86` responde desde la red móvil

Si estás en WiFi o fuera de Cuba, el streaming sigue funcionando pero consume megas normalmente.

## Formatos de video soportados

El servidor detecta automáticamente por extensión:

| Ext | Tipo MIME |
|-----|-----------|
| .mp4 | video/mp4 |
| .mkv | video/x-matroska |
| .webm | video/webm |
| .avi | video/x-msvideo |
| .mov | video/quicktime |
| .m4v | video/x-m4v |
| .flv | video/x-flv |
| .wmv | video/x-ms-wmv |
| .3gp | video/3gpp |
| .ogv | video/ogg |
