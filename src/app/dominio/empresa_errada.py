CATEGORIA_PERMITIDA = "transferencia_saida"


def eh_empresa_errada(
    *,
    empresa_id: int,
    destino_id: int | None,
    cancelada: bool | None,
    categoria: str,
) -> bool:
    return (
        destino_id is not None
        and destino_id != empresa_id
        and cancelada is not True
        and categoria != CATEGORIA_PERMITIDA
    )
