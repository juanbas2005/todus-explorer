# El sistema UDYAT — Zero-rated para ToDus

## Qué es UDYAT

"Udyat" significa **"usando direct"** en el argot de los desarrolladores de ToDus. Es la técnica que evita que el tráfico hacia `s3.todus.cu` consuma datos móviles en la red de ETECSA.

## El truco: IP directa en vez de DNS

ETECSA tiene una IP interna (`152.207.206.86`) que sirve `s3.todus.cu` de forma gratuita. Cuando accedes a esa IP desde datos móviles de ETECSA, el tráfico no cuenta para tu plan.

El DNS público (`s3.todus.cu` → IP real) no funciona igual — resuelve a la IP correcta pero el tráfico puede pasar por los medidores de uso.

## Los 5 trucos de udyat

### 1. Resolución DNS directa
```bash
--resolve "s3.todus.cu:443:152.207.206.86"
```
Fuerza a curl a conectar a la IP `152.207.206.86` cuando pida `s3.todus.cu`. Esto también manda el SNI correcto en el handshake TLS.

### 2. Host header override
```bash
-H "Host: s3.todus.cu"
```
El servidor ToDus usa el header `Host` para saber a qué dominio sirves. Sin esto, recibiría la petición como para `152.207.206.86` y la rechazaría.

### 3. User-Agent exacto
```bash
-A "Wget/1.21.3"
```
ToDus filtra o prioriza por User-Agent. Usar `Wget/1.21.3` es el UA exacto que usa el sistema ToDus.

### 4. TLS permisivo
```bash
--insecure
```
La IP gratuita tiene un certificado auto-firmado o diferente al oficial. Sin `--insecure`, curl rechaza la conexión.

### 5. HTTP/1.1 forzado
```bash
--http1.1
```
Some servers behave better with HTTP/1.1. Avoids HTTP/2 multiplexing issues.

## Implementación en Python

En `s3_server.py`, el método `stream_s3()` hace:

```python
cmd = [
    "curl", "-sS", "-m", "60", "-D", "-", "-o", "-",
    "--http1.1", "--insecure",
    "-A", "Wget/1.21.3",
    "-H", "Host: s3.todus.cu",
    "-H", "Accept: */*",
    "--resolve", f"s3.todus.cu:443:152.207.206.86",
    f"https://s3.todus.cu/stream/{key}"
]
```

Esto se usa para streaming de video y cualquier otra descarga por el proxy.

## Implementación en bash

En `udyat/udyat-test.sh`:

```bash
curl "${CURL_COMMON[@]}" \
    --resolve "s3.todus.cu:443:152.207.206.86" \
    "https://s3.todus.cu$PATH_URL"
```

## Notas

- La IP `152.207.206.86` es específica para la red móvil de ETECSA Cuba
- En WiFi o fuera de Cuba, la IP puede no responder o responder lentamente
- El script hace un **pre-flight check**: si la IP no responde en 3 segundos, cae a HTTPS directo (con megas)
