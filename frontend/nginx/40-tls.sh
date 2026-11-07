#!/bin/sh
set -eu

CERTS="${ERP_TLS_CERTS:-/etc/nginx/certs}"
MODELOS="${ERP_NGINX_MODELOS:-/etc/nginx/erp}"
DESTINO="${ERP_NGINX_CONF:-/etc/nginx/conf.d/default.conf}"

if [ -f "$CERTS/fullchain.pem" ] && [ -f "$CERTS/privkey.pem" ]; then
    cp "$MODELOS/https.conf" "$DESTINO"
    echo "40-tls.sh: certificado em $CERTS, servindo HTTPS (80 redireciona para 443)"
else
    cp "$MODELOS/http.conf" "$DESTINO"
    echo "40-tls.sh: sem fullchain.pem e privkey.pem em $CERTS, servindo so HTTP"
fi
