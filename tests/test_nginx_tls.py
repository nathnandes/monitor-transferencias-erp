import os
import shutil
import subprocess
from pathlib import Path

import pytest

NGINX = Path(__file__).resolve().parent.parent / "frontend" / "nginx"
SH = shutil.which("sh")


def _ler(nome: str) -> str:
    return (NGINX / nome).read_text(encoding="utf-8")


def test_https_redireciona_a_80_e_manda_hsts():
    https = _ler("https.conf")
    assert "listen 443 ssl" in https
    assert "return 301 https://$host$request_uri" in https
    assert "ssl_certificate /etc/nginx/certs/fullchain.pem" in https
    assert "ssl_certificate_key /etc/nginx/certs/privkey.pem" in https
    assert 'set $hsts "max-age=31536000"' in https


def test_cada_location_manda_hsts_e_os_cabecalhos_de_seguranca():
    blocos = _ler("locations.conf").split("\nlocation ")[1:]
    assert len(blocos) == 3
    for bloco in blocos:
        assert "add_header Strict-Transport-Security $hsts always;" in bloco
        assert 'add_header X-Content-Type-Options "nosniff" always;' in bloco


def test_http_puro_nao_manda_hsts():
    http = _ler("http.conf")
    assert "listen 80" in http and "443" not in http
    assert 'set $hsts ""' in http


def test_dockerfile_instala_o_script_e_as_duas_configuracoes():
    dockerfile = (NGINX.parent / "Dockerfile").read_text(encoding="utf-8")
    assert "/docker-entrypoint.d/40-tls.sh" in dockerfile
    assert "EXPOSE 80 443" in dockerfile


def _rodar_script(tmp_path: Path, *, com_certificado: bool) -> str:
    certs, modelos, conf = tmp_path / "certs", tmp_path / "erp", tmp_path / "conf.d"
    for pasta in (certs, modelos, conf):
        pasta.mkdir(parents=True)
    for nome in ("http.conf", "https.conf"):
        shutil.copy(NGINX / nome, modelos / nome)
    if com_certificado:
        (certs / "fullchain.pem").write_text("CERT")
        (certs / "privkey.pem").write_text("KEY")
    ambiente = {
        **os.environ,
        "ERP_TLS_CERTS": str(certs),
        "ERP_NGINX_MODELOS": str(modelos),
        "ERP_NGINX_CONF": str(conf / "default.conf"),
    }
    subprocess.run([SH, str(NGINX / "40-tls.sh")], env=ambiente, check=True)
    return (conf / "default.conf").read_text(encoding="utf-8")


@pytest.mark.skipif(SH is None, reason="sem sh no PATH")
def test_script_liga_https_so_com_certificado_e_chave(tmp_path):
    assert "listen 443 ssl" in _rodar_script(tmp_path / "com", com_certificado=True)
    assert "443" not in _rodar_script(tmp_path / "sem", com_certificado=False)


def test_cada_location_manda_content_security_policy():
    for bloco in _ler("locations.conf").split("\nlocation ")[1:]:
        csp = next(linha for linha in bloco.splitlines() if "Content-Security-Policy" in linha)
        for diretiva in (
            "default-src 'self'",
            "script-src 'self'",
            "object-src 'none'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
        ):
            assert diretiva in csp, (diretiva, bloco.splitlines()[0])
        assert "unsafe-eval" not in csp
