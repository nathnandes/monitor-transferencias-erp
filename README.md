# Monitor de transferências

Sistema que lê os dados de um ERP e entrega à diretoria de uma rede de 6 empresas o que o ERP não
mostra: transferências paradas entre as lojas, divergências de quantidade, notas com erro, vendas,
estoque e alertas automáticos. Inclui um modelo de IA que aponta as notas fora do padrão e explica o
motivo.

> **Esta é uma versão pública e limpa.** Empresa, lojas, códigos de operação e integração foram
> trocados por nomes fictícios, e os dados de demonstração são inventados. Para garantir que nada
> interno vazasse, os comentários do código e a documentação interna foram removidos.

## O que ele faz

| Módulo | O que entrega |
|---|---|
| **Transferências** | Saída sem entrada no destino, prazo por rota, divergência por item em R$, conferência fiscal e tratativas |
| **IA: fora do padrão** | Modelo não supervisionado que sinaliza notas diferentes do histórico da rota, com o motivo em texto |
| **Alertas** | Motor de regras com abertura, escalada e resolução, enviado por Telegram e WhatsApp, com destinos configuráveis |
| **Resumo diário** | Mensagem automática para a diretoria |
| **Estoque** | Saldo por empresa e local, cobertura, livro de movimentação, balanços e estoque baixo pelo giro |
| **Vendas e financeiro** | Faturamento, canais, categorias, vendedores, metas, descontos e recebimentos |
| **Painel** | Dashboard com filtro global, modo TV e exportação |
| **Acesso** | Login local com JWT e Argon2id, permissões por módulo, perfis e auditoria |

## Arquitetura

```text
 ERP (API, só leitura)
        │
        ▼
 Worker de sincronização ──► PostgreSQL ◄── API FastAPI ◄── React + TypeScript
                                ▲   ▲
        Worker de alertas ──────┘   └────── Worker do detector de anomalias
                │                                (scikit-learn)
                ▼
     Telegram · WhatsApp
```

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL
- **IA:** scikit-learn (IsolationForest), em processo próprio: a API não carrega a biblioteca
- **Frontend:** React, TypeScript, Vite, Tailwind CSS, Recharts
- **Infra:** Docker Compose, nginx, GitHub Actions

Algumas decisões de projeto:

- **Só leitura no ERP.** Nada é escrito nele, e o acesso passa por uma lista de rotas permitidas.
- **Sincronização idempotente.** Repetir uma leitura não duplica nada.
- **Outbox de notificações.** O alerta é gravado na mesma transação da regra e enviado depois, então
  falhar no Telegram não perde o aviso.
- **Sem rede nos testes.** A suíte bloqueia qualquer conexão externa.

## O detector de anomalias

O método, os resultados e os limites estão no repositório próprio do detector:
[detector-anomalias-transferencias](https://github.com/nathnandes/detector-anomalias-transferencias).
Em dados sintéticos, conferindo as mesmas 2% das notas, ele encontra 83% das anomalias injetadas, e
uma regra simples encontra 52%. **Esses números não medem a eficácia com dados reais**, porque o
gerador de dados foi escrito junto com o detector.

Aqui está a integração dele: `src/app/workers/anomalias.py`, `src/app/services/anomalias.py`, a
regra `transferencia_anomala` e o painel em Transferências › Controle.

## Rodar com dados de demonstração

Precisa de Python 3.12, Node.js 20.19+ e Docker. Sem o ERP, o sistema funciona com dados inventados.

```bash
cp .env.example .env
```

No `.env`, preencha `JWT_SECRET` com um texto aleatório longo e troque `SUA_SENHA` em `DATABASE_URL`
pelo valor de `POSTGRES_PASSWORD`. Depois:

```bash
docker compose up -d db
python -m venv .venv && source .venv/bin/activate
pip install -c constraints.txt -e ".[dev]"
alembic upgrade head
python -m app.scripts.demo_anomalias seed
ANOMALIAS_JANELA_AVALIACAO_DIAS=30 python -m app.workers.anomalias --uma-vez
python -m app.scripts.create_admin
python -m uvicorn app.main:app --app-dir src
```

Em outro terminal:

```bash
npm --prefix frontend ci
npm --prefix frontend run dev
```

Abra `http://localhost:5173/transferencias/controle?periodo=tudo`. Os dados inventados terminam
ontem, então o filtro padrão "Hoje" aparece vazio.

## Testes

```bash
pytest
npm --prefix frontend test
```

Os testes que usam banco exigem o PostgreSQL no ar e são pulados sem ele.

## Limites

- A integração com o ERP foi generalizada nesta versão: os nomes de rotas são fictícios, então ela
  não conecta a um ERP real sem ajustes.
- O detector só foi testado com dados sintéticos.

Desenvolvido com apoio do Claude Code.
