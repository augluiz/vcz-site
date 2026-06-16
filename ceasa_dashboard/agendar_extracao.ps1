# Registra duas tarefas agendadas para rodar automaticamente em dias uteis:
#   CEASA-Extracao  — baixa cotacoes de preco do CEASA/SC (3 tentativas)
#   CEASA-Clima     — atualiza dados meteorologicos SC + previsao do tempo
#
# Logica das tentativas do CEASA:
#   10:30 — primeira tentativa (PDF publicado ~11:20 BRT, mas pode ser mais cedo)
#   11:30 — segunda tentativa, caso o PDF ainda nao estivesse disponivel as 10:30
#   12:15 — terceira tentativa (horario esperado de publicacao confiavel)
#   14:05 — quarta tentativa de seguranca
#
# Os scripts pulam dados ja presentes — rodar multiplas vezes e seguro.
#
# COMO USAR: clique com botao direito neste arquivo > "Executar como administrador"
# Para remover tudo: Unregister-ScheduledTask -TaskName "CEASA-Extracao" -Confirm:$false
#                    Unregister-ScheduledTask -TaskName "CEASA-Clima"    -Confirm:$false

$PythonExe = (Get-Command python).Source
$WorkDir   = "C:\Users\augus\ceasa_dashboard"

# ---------------------------------------------------------------
# TAREFA 1: Extracao de cotacoes CEASA (3 tentativas por dia)
# ---------------------------------------------------------------
$ActionCeasa = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "extrair_ceasa.py" `
    -WorkingDirectory $WorkDir

$Trigger1 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "10:30"
$Trigger2 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "11:30"
$Trigger3 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "12:15"
$Trigger4 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "14:05"

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

Register-ScheduledTask `
    -TaskName "CEASA-Extracao" `
    -Action   $ActionCeasa `
    -Trigger  @($Trigger1, $Trigger2, $Trigger3, $Trigger4) `
    -Settings $Settings `
    -RunLevel Highest `
    -Force

Write-Host "Tarefa 'CEASA-Extracao' registrada." -ForegroundColor Green

# ---------------------------------------------------------------
# TAREFA 2: Dados meteorologicos (1x por dia, as 08:00)
# O clima nao muda no meio do dia — uma execucao diaria e suficiente.
# Historico e append-only; previsao e sobrescrita a cada run.
# ---------------------------------------------------------------
$ActionClima = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "clima_sc.py" `
    -WorkingDirectory $WorkDir

$TriggerClima = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday `
    -At "08:00"

Register-ScheduledTask `
    -TaskName "CEASA-Clima" `
    -Action   $ActionClima `
    -Trigger  $TriggerClima `
    -Settings $Settings `
    -RunLevel Highest `
    -Force

Write-Host "Tarefa 'CEASA-Clima' registrada." -ForegroundColor Green

Write-Host ""
Write-Host "Resumo do agendamento:"
Write-Host "  CEASA-Extracao : seg-sex as 10:30 / 11:30 / 12:15 / 14:05"
Write-Host "  CEASA-Clima    : todos os dias as 08:00"
Write-Host ""
Write-Host "Para rodar agora:"
Write-Host "  Start-ScheduledTask -TaskName 'CEASA-Extracao'"
Write-Host "  Start-ScheduledTask -TaskName 'CEASA-Clima'"
