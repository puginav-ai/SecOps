#!/bin/sh
# Самоподписанный сертификат для локальной разработки.
# Прод: сертификат внутреннего УЦ, положить как ops/certs/tls.crt + tls.key.
set -e
dir="$(cd "$(dirname "$0")" && pwd)"

if [ -f "$dir/tls.crt" ]; then
    echo "ops/certs/tls.crt уже существует — не перезаписываю"
    exit 0
fi

openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
    -keyout "$dir/tls.key" -out "$dir/tls.crt" \
    -subj "/CN=localhost/O=SecOps Dev" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
chmod 600 "$dir/tls.key"
echo "Готово: ops/certs/tls.crt, ops/certs/tls.key"
