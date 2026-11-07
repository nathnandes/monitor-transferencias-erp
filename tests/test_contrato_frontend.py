from app.scripts.exportar_openapi import DESTINO, gerar, serializar


def test_openapi_do_frontend_esta_em_dia():
    assert DESTINO.exists(), "rode: python -m app.scripts.exportar_openapi"
    atual = DESTINO.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert atual == serializar(gerar()), (
        "frontend/openapi.json desatualizado: rode python -m app.scripts.exportar_openapi "
        "e, no frontend, npm run gen:api"
    )


def test_nomes_dos_schemas_do_openapi_sao_unicos_e_estaveis():
    from app.main import create_app

    nomes = create_app().openapi()["components"]["schemas"]
    assert [n for n in nomes if "__" in n] == []
