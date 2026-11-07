<#
.SYNOPSIS
  Backup do PostgreSQL proprio (docker-compose.prod.yml) com rotacao.

.DESCRIPTION
  Roda pg_dump DENTRO do container "db" (formato custom, comprimido) e grava
  em .\backups\erp_AAAAMMDD_HHMMSS.dump. Apaga os dumps mais antigos que
  -Dias. Nenhuma senha passa pela linha de comando: o pg_dump usa as
  variaveis do proprio container.

  Agendar (Agendador de Tarefas do Windows), todo dia as 02:00:
    schtasks /Create /SC DAILY /ST 02:00 /TN "ERP backup" `
      /TR "powershell -NoProfile -File C:\caminho\erp-automation\scripts\backup.ps1"

  Restaurar: ver docs/operacao.md.

  Copia externa: backup no mesmo disco do banco nao protege contra perda do
  disco. Com -Copia (ou a variavel de ambiente BACKUP_COPIA), o dump tambem
  e copiado para outro lugar (compartilhamento de rede, pasta sincronizada
  com a nuvem, disco externo), conferido pelo tamanho e rodado com os mesmos
  -Dias. Falha na copia = o script falha (o agendador mostra o erro).

  Teste de restauracao: scripts\testar-restauracao.ps1 (semanal).

.PARAMETER Dias
  Quantos dias de backup manter. Padrao: 14.

.PARAMETER Copia
  Pasta de destino da copia externa, ex.: \\servidor\backups\erp.
  Padrao: variavel de ambiente BACKUP_COPIA (vazia = sem copia).
param([int]$Dias = 14, [string]$Copia = $env:BACKUP_COPIA)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

$pasta = Join-Path $raiz "backups"
New-Item -ItemType Directory -Force $pasta | Out-Null

$nome = "erp_{0}.dump" -f (Get-Date -Format "yyyyMMdd_HHmmss")
$compose = @("compose", "-f", "docker-compose.prod.yml")

& docker @compose exec -T db sh -c "pg_dump -U `"`$POSTGRES_USER`" -d `"`$POSTGRES_DB`" -Fc -f /backups/$nome"
if ($LASTEXITCODE -ne 0) { throw "pg_dump falhou (codigo $LASTEXITCODE)" }

$arquivo = Join-Path $pasta $nome
if (-not (Test-Path $arquivo) -or (Get-Item $arquivo).Length -eq 0) {
    throw "backup vazio ou ausente: $arquivo"
}
Write-Output ("backup ok: {0} ({1:N0} KB)" -f $arquivo, ((Get-Item $arquivo).Length / 1KB))

Get-ChildItem $pasta -Filter "erp_*.dump" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$Dias) } |
    ForEach-Object { Remove-Item $_.FullName -Confirm:$false; Write-Output "removido: $($_.Name)" }

if ($Copia) {
    New-Item -ItemType Directory -Force $Copia | Out-Null
    $destino = Join-Path $Copia $nome
    Copy-Item $arquivo $destino -Force
    if ((Get-Item $destino).Length -ne (Get-Item $arquivo).Length) {
        throw "copia externa com tamanho diferente: $destino"
    }
    Write-Output "copia externa ok: $destino"
    Get-ChildItem $Copia -Filter "erp_*.dump" |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$Dias) } |
        ForEach-Object { Remove-Item $_.FullName -Confirm:$false; Write-Output "removido da copia: $($_.Name)" }
} else {
    Write-Warning "sem copia externa (use -Copia ou BACKUP_COPIA): o backup esta so neste disco"
}
