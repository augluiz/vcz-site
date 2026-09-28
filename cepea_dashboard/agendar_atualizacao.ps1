# Registra uma tarefa agendada para rodar atualizar_diario.py todo dia.
#
# Diferente do CEASA (que espera a publicacao de um PDF em horario incerto),
# as paginas de indicador do CEPEA sao atualizadas ao longo do dia e ficam
# disponiveis o tempo todo — uma unica execucao por dia e suficiente.
# Roda as 09:00, depois que o pregao do dia anterior ja fechou.
#
# O script pula datas ja presentes — rodar mais de uma vez no mesmo dia e seguro.
#
# COMO USAR: clique com botao direito neste arquivo > "Executar como administrador"
# Para remover: Unregister-ScheduledTask -TaskName "CEPEA-Atualizacao" -Confirm:$false

# "Get-Command python" costuma resolver para o atalho generico da Microsoft
# Store (WindowsApps\python.exe), que so funciona numa sessao interativa —
# rodando via Tarefa Agendada ele nao faz nada (sai com sucesso, mas sem
# executar o script de verdade). Por isso procuramos o .exe real, dentro
# da pasta versionada do pacote instalado.
$stub = (Get-Command python).Source
$real = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.*\python.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
$PythonExe = if ($real) { $real.FullName } else { $stub }
$WorkDir   = "C:\Users\augus\vcz-site\cepea_dashboard"

$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "atualizar_diario.py" `
    -WorkingDirectory $WorkDir

$Trigger = New-ScheduledTaskTrigger `
    -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday -At "09:00"

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName "CEPEA-Atualizacao" `
    -Action   $Action `
    -Trigger  $Trigger `
    -Settings $Settings `
    -Force

Write-Host "Tarefa 'CEPEA-Atualizacao' registrada — roda todo dia as 09:00." -ForegroundColor Green
Write-Host ""
Write-Host "Para rodar agora:"
Write-Host "  Start-ScheduledTask -TaskName 'CEPEA-Atualizacao'"
Write-Host ""
Write-Host "NOTA: os indicadores Leite, Suino e Ovinos nao atualizam por aqui"
Write-Host "(o CEPEA so publica esses como serie mensal ou sem tabela diaria"
Write-Host "na pagina publica). Os outros 15 produtos atualizam normalmente."
