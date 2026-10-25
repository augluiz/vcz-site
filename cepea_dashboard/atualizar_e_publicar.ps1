# ─────────────────────────────────────────────────────────────────────
#  CEPEA — coleta diaria + publicacao
# ─────────────────────────────────────────────────────────────────────
#
#  POR QUE ESTE SCRIPT EXISTE
#  A coleta rodava no GitHub Actions, mas a Cloudflare do CEPEA bloqueia
#  o IP dos runners (datacenter). Confirmado em 25/10/2026: o mesmo
#  script roda sem erro a partir de um IP residencial. Entao a coleta
#  passou para a maquina local, e este script faz o que o workflow fazia:
#  coletar, commitar e publicar.
#
#  COMO AGENDAR:  rodar agendar_atualizacao.ps1 (uma vez)
#  COMO TESTAR:   powershell -ExecutionPolicy Bypass -File atualizar_e_publicar.ps1
#  LOG:           %LOCALAPPDATA%\vcz-cepea\cepea.log
# ─────────────────────────────────────────────────────────────────────

# NAO usar $ErrorActionPreference = "Stop" aqui.
# O git escreve progresso no stderr mesmo quando da certo; no PowerShell 5.1
# isso vira ErrorRecord e derruba o script com "NativeCommandError" numa
# execucao que foi bem-sucedida. Pelo mesmo motivo nao usamos $? apos
# comando nativo — a checagem confiavel e $LASTEXITCODE (0 = sucesso).
$Repo  = "C:\Users\augus\vcz-site"
$Dados = "cepea_dashboard/dados"

Set-Location $Repo

# Log em arquivo: rodando pelo Agendador nao ha console pra ver o que houve,
# e essa coleta ja ficou tres semanas quebrada sem deixar rastro. Fica fora
# do repositorio de proposito, pra nao virar commit todo dia.
$LogDir = "$env:LOCALAPPDATA\vcz-cepea"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
Start-Transcript -Path "$LogDir\cepea.log" -Append | Out-Null

# Toda saida passa por aqui, pra garantir que o transcript seja fechado.
function Finalizar([int]$codigo, [string]$mensagem) {
    Write-Output "CEPEA: $mensagem"
    try { Stop-Transcript | Out-Null } catch { }
    exit $codigo
}

Write-Output ""
Write-Output "[$(Get-Date -Format 'yyyy-MM-dd HH:mm')] CEPEA: iniciando"

# ── 1. Descobrir o Python de verdade ─────────────────────────────────
# NAO chamar "python" direto: "Get-Command python" resolve para o atalho
# da Microsoft Store (WindowsApps\python.exe), que so funciona em sessao
# interativa. Sob o Agendador ele NAO executa o script e ainda sai com
# codigo 0 — ou seja, tarefa verde todo dia sem coletar nada. Foi
# exatamente o que aconteceu no primeiro teste em 25/10/2026.
$stub = (Get-Command python -ErrorAction SilentlyContinue).Source
$real = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.*\python.exe" `
        -ErrorAction SilentlyContinue | Select-Object -First 1
$PythonExe = if ($real) { $real.FullName } else { $stub }

if (-not $PythonExe) { Finalizar 1 "python nao encontrado. Abortando." }
Write-Output "CEPEA: usando $PythonExe"

# ── 2. Coleta ────────────────────────────────────────────────────────
# atualizar_diario.py sai com codigo 1 so quando a MAIORIA dos produtos
# falha. Produto isolado com erro mantem o valor anterior e nao derruba
# a rodada (Leite, Suino e Ovinos sao serie mensal e sempre dao erro aqui).
Set-Location "$Repo\cepea_dashboard"
& $PythonExe atualizar_diario.py
$coletaExit = $LASTEXITCODE
Set-Location $Repo

if ($coletaExit -ne 0) { Finalizar 1 "coleta falhou (exit $coletaExit). Nada sera commitado." }

# ── 3. Ha mudanca real nos dados? ────────────────────────────────────
# "git status --porcelain <caminho>" lista so o que mudou naquele caminho.
# Vazio = nenhum dado novo (acontece em fim de semana e feriado).
$mudou = git status --porcelain -- $Dados
if (-not $mudou) { Finalizar 0 "nenhum dado novo. Nada a publicar." }

# ── 4. Commit APENAS dos dados ───────────────────────────────────────
# IMPORTANTE: o repositorio costuma ter arquivos de outros trabalhos em
# staging. Por isso commitamos por caminho explicito (git commit -- <path>),
# que ignora o resto do indice em vez de varrer tudo junto.
git add -- $Dados
git commit -m "data: atualiza indicadores CEPEA $(Get-Date -Format 'yyyy-MM-dd')" -- $Dados
if ($LASTEXITCODE -ne 0) { Finalizar 1 "commit falhou." }

# ── 5. Publicar ──────────────────────────────────────────────────────
# A automacao do CEASA tambem commita no master varias vezes por dia,
# entao o remoto costuma estar a frente e o push direto e rejeitado.
git push origin master
if ($LASTEXITCODE -eq 0) { Finalizar 0 "publicado." }

Write-Output "CEPEA: push rejeitado (remoto a frente). Tentando integrar..."
git fetch origin
git merge origin/master -m "Merge dados automaticos antes de publicar CEPEA"

if ($LASTEXITCODE -ne 0) {
    # O merge falha quando ha arquivos em staging de outro trabalho.
    # NAO forcamos nada: o commit fica local e o usuario resolve quando puder.
    Write-Output "       O commit dos dados esta salvo localmente, nada se perdeu."
    Write-Output "       Para publicar: limpe ou commite o staging pendente e rode 'git push'."
    Finalizar 1 "merge bloqueado (ha arquivos em staging de outro trabalho)."
}

git push origin master
if ($LASTEXITCODE -eq 0) { Finalizar 0 "publicado apos merge." }
Finalizar 1 "push falhou mesmo apos merge."
