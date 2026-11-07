from pydantic import SecretStr

from app.erp import ConsultorErpApi, ErpApiClient, PedidoToken, ProvedorToken
from app.erp.schemas import CONTENT_TYPE_TOKEN, GRANT_TYPE_TOKEN, cabecalho_autorizacao
from tests.bloqueio_rede import TENTATIVAS
from tests.erpapi_fakes import CLIENT_ID, CLIENT_SECRET, SENHA, USUARIO, criar_settings


def test_client_cumpre_os_contratos_sem_abrir_conexao():
    antes = len(TENTATIVAS)
    with ErpApiClient(criar_settings(enabled=False)) as client:
        assert isinstance(client, ProvedorToken)
        assert isinstance(client, ConsultorErpApi)
    assert len(TENTATIVAS) == antes


def test_contratos_so_tem_operacoes_de_consulta():
    escrita = ("gravar", "salvar", "enviar", "incluir", "alterar", "excluir", "criar", "post")
    for protocolo in (ProvedorToken, ConsultorErpApi):
        nomes = [n for n in vars(protocolo) if not n.startswith("_")]
        assert not [n for n in nomes if n.startswith(escrita)], (protocolo.__name__, nomes)


def _pedido() -> PedidoToken:
    return PedidoToken(
        client_id=CLIENT_ID, client_secret=CLIENT_SECRET, username=USUARIO, password=SENHA
    )


def test_pedido_de_token_segue_o_formato_do_manual():
    form = _pedido().to_form()

    assert list(form) == ["client_id", "grant_type", "client_secret", "username", "password"]
    assert form["grant_type"] == GRANT_TYPE_TOKEN == "password"
    assert form["client_secret"] == CLIENT_SECRET
    assert form["password"] == SENHA
    assert CONTENT_TYPE_TOKEN == "application/x-www-form-urlencoded"


def test_pedido_de_token_nao_expoe_segredos_no_repr():
    pedido = _pedido()
    for texto in (repr(pedido), str(pedido), pedido.model_dump_json()):
        assert SENHA not in texto
        assert CLIENT_SECRET not in texto


def test_cabecalho_de_autorizacao_usa_bearer():
    assert cabecalho_autorizacao(SecretStr("tok-ficticio")) == {
        "Authorization": "Bearer tok-ficticio"
    }
