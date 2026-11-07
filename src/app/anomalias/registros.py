from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RegistroTransferencia:
    id: str
    origem: str
    destino: str
    valor: float
    emitida_em: datetime
    recebida_em: datetime | None
    quantidade_itens: int
    quantidade_enviada: float
    quantidade_recebida: float | None

    @property
    def rota(self) -> tuple[str, str]:
        return (self.origem, self.destino)

    @property
    def pendente(self) -> bool:
        return self.recebida_em is None
