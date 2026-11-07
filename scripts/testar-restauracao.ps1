<#
.SYNOPSIS
  Prova que o backup mais recente restaura: restaura num banco temporario e confere.

.DESCRIPTION
  Backup que nunca foi restaurado nao e backup confiavel. Este script pega o
  dump mais recente de .\backups (ou -Arquivo), restaura num banco temporario
  (erp_verificacao) DENTRO do container "db", confere que o schema veio
  (alembic_version) e que ha dados (empresas), e apaga o banco temporario.
  O banco de producao nao e tocado.

  Agendar (Agendador de Tarefas do Windows), todo domingo as 04:00:
    schtasks /Create /SC WEEKLY /D SUN /ST 04:00 /TN "ERP testar restauracao" `
      /TR "powershell -NoProfile -File C:\caminho\erp-automation\scripts\testar-restauracao.ps1"

.PARAMETER Arquivo
  Nome do dump em .\backups (ex.: erp_20261014_020000.dump). Padrao: o mais recente.
param([string]$Arquivo = "")

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

$pasta = Join-Path $raiz "backups"
if (-not $Arquivo) {
    $ultimo = Get-ChildItem $pasta -Filter "erp_*.dump" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $ultimo) { throw "nenhum backup em $pasta" }
    $Arquivo = $ultimo.Name
}
if (-not (Test-Path (Join-Path $pasta $Arquivo))) { throw "backup nao encontrado: $Arquivo" }

$compose = @("compose", "-f", "docker-compose.prod.yml")
$banco = "erp_verificacao"

function Invoke-NoDb([string]$comando) {
    & docker @compose exec -T db sh -c $comando
    if ($LASTEXITCODE -ne 0) { throw "falhou (codigo $LASTEXITCODE): $comando" }
}

Write-Output "restaurando $Arquivo em $banco..."
try {
    Invoke-NoDb "dropdb --if-exists -U `"`$POSTGRES_USER`" $banco && createdb -U `"`$POSTGRES_USER`" $banco"
    Invoke-NoDb "pg_restore -U `"`$POSTGRES_USER`" -d $banco --no-owner --exit-on-error /backups/$Arquivo"

    $versao = (& docker @compose exec -T db sh -c "psql -U `"`$POSTGRES_USER`" -d $banco -tAc 'SELECT version_num FROM alembic_version'").Trim()
    $empresas = (& docker @compose exec -T db sh -c "psql -U `"`$POSTGRES_USER`" -d $banco -tAc 'SELECT count(*) FROM empresas'").Trim()
    if (-not $versao) { throw "restaurado sem alembic_version: o schema nao veio" }
    if ([int]$empresas -lt 1) { throw "restaurado sem empresas: o dump parece vazio" }
    Write-Output "restauracao ok: $Arquivo (schema $versao, $empresas empresas)"
} finally {
    & docker @compose exec -T db sh -c "dropdb --if-exists -U `"`$POSTGRES_USER`" $banco" | Out-Null
}
