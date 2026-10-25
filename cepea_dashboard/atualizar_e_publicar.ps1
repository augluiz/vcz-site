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
#  COMO AGENDAR: rodar agendar_atualizacao.ps1 como administrador.
#  COMO TESTAR AGORA:  powershell -File atualizar_e_publicar.ps1
# ─────────────────────────────────────────────────────────────────────

# NAO usar $ErrorActionPreference = "Stop" aqui.
# O git escreve progresso no stderr mesmo quando da certo; no PowerShell 5.1
# isso vira ErrorRecord e derruba o script com "NativeCommandError" numa
# execucao que foi bem-sucedida. Pelo mesmo motivo nao usamos $? apos
# comando nativo — a checagem confiavel e $LASTEXITCODE (0 = sucesso).
$Repo = "C:\Users\augus\vcz-site"
$Dados = "cepea_dashboard/dados"

Set-Location $Repo

Write-Output "[$(Get-Date -Format 'yyyy-MM-dd HH:mm')] CEPEA: iniciando coleta"

# ── 1. Coleta ────────────────────────────────────────────────────────
# O script sai com codigo 1 so quando a MAIORIA dos produtos falha.
# Produto isolado com erro mantem o valor anterior e nao derruba a rodada.
Set-Location "$Repo\cepea_dashboard"
python atualizar_diario.py
$coletaExit = $LASTEXITCODE
Set-Location $Repo

if ($coletaExit -ne 0) {
    Write-Output "CEPEA: coleta falhou (exit $coletaExit). Nada sera commitado."
    exit 1
}

# ── 2. Ha mudanca real nos dados? ────────────────────────────────────
# "git status --porcelain <caminho>" lista so o que mudou naquele caminho.
# Vazio = nenhum dado novo hoje (acontece em fim de semana e feriado).
$mudou = git status --porcelain -- $Dados
if (-not $mudou) {
    Write-Output "CEPEA: nenhum dado novo hoje. Nada a publicar."
    exit 0
}

# ── 3. Commit APENAS dos dados ───────────────────────────────────────
# IMPORTANTE: o repositorio costuma ter arquivos de outros trabalhos
# em staging. Por isso commitamos por caminho explicito (git commit -- <path>),
# que ignora o resto do indice em vez de varrer tudo junto.
git add -- $Dados
git commit -m "data: atualiza indicadores CEPEA $(Get-Date -Format 'yyyy-MM-dd')" -- $Dados
if ($LASTEXITCODE -ne 0) { Write-Output "CEPEA: commit falhou."; exit 1 }

# ── 4. Publicar ──────────────────────────────────────────────────────
# A automacao do CEASA tambem commita no master varias vezes por dia,
# entao o remoto costuma estar a frente e o push direto e rejeitado.
git push origin master
if ($LASTEXITCODE -eq 0) {
    Write-Output "CEPEA: publicado."
    exit 0
}

Write-Output "CEPEA: push rejeitado (remoto a frente). Tentando integrar..."
git fetch origin
git merge origin/master -m "Merge dados automaticos antes de publicar CEPEA"

if ($LASTEXITCODE -ne 0) {
    # O merge falha quando ha arquivos em staging de outro trabalho.
    # Nesse caso NAO forcamos nada: o commit fica local e o usuario resolve.
    Write-Output ""
    Write-Output "CEPEA: merge bloqueado (ha arquivos em staging de outro trabalho)."
    Write-Output "       O commit dos dados esta salvo localmente, nada se perdeu."
    Write-Output "       Para publicar: limpe ou commite o staging pendente e rode 'git push'."
    exit 1
}

git push origin master
if ($LASTEXITCODE -eq 0) {
    Write-Output "CEPEA: publicado apos merge."
} else {
    Write-Output "CEPEA: push falhou mesmo apos merge."
    exit 1
}
