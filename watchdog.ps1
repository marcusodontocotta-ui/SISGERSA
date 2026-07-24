# SISGERSA Watchdog - Monitora e reinicia servidor + Cloudflare Tunnel
# Uso: powershell -ExecutionPolicy Bypass -File watchdog.ps1

$ProjectDir = "C:\Users\T-GAMER\Documents\Default Project\medical_db"
$ServerPort = 8000
$CheckInterval = 15

Write-Host "=== SISGERSA Watchdog ===" -ForegroundColor Green
Write-Host "Monitorando servidor (porta $ServerPort) e Cloudflare Tunnel..." -ForegroundColor Cyan
Write-Host ""

function Start-Server {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Iniciando servidor uvicorn..." -ForegroundColor Yellow
    $proc = Start-Process -FilePath "python" `
        -ArgumentList "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "$ServerPort" `
        -WorkingDirectory $ProjectDir `
        -PassThru -WindowStyle Minimized
    Start-Sleep -Seconds 3
    return $proc
}

function Start-Tunnel {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Iniciando Cloudflare Tunnel..." -ForegroundColor Yellow
    $proc = Start-Process -FilePath "cloudflared" `
        -ArgumentList "tunnel", "--url", "http://localhost:$ServerPort" `
        -WorkingDirectory $ProjectDir `
        -RedirectStandardOutput "$ProjectDir\tunnel_output.txt" `
        -RedirectStandardError "$ProjectDir\tunnel_error.txt" `
        -PassThru -WindowStyle Minimized
    Start-Sleep -Seconds 5
    return $proc
}

function Test-ServerAlive {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:$ServerPort/api/status" -TimeoutSec 5 -UseBasicParsing
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

# Inicializar
$serverProc = Start-Server
$tunnelProc = Start-Tunnel
$consecutiveFails = 0

Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Watchdog rodando. Pressione Ctrl+C para parar." -ForegroundColor Green
Write-Host ""

while ($true) {
    Start-Sleep -Seconds $CheckInterval

    # Verificar servidor
    $serverAlive = Test-ServerAlive

    if (-not $serverAlive) {
        $consecutiveFails++
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Servidor NAO respondeu (tentativa $consecutiveFails)" -ForegroundColor Red

        if ($consecutiveFails -ge 3) {
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Reiniciando servidor..." -ForegroundColor Yellow
            try { Stop-Process -Id $serverProc.Id -Force -ErrorAction SilentlyContinue } catch {}
            Start-Sleep -Seconds 2
            $serverProc = Start-Server
            $consecutiveFails = 0
        }
    } else {
        if ($consecutiveFails -gt 0) {
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Servidor recuperado!" -ForegroundColor Green
        }
        $consecutiveFails = 0
    }

    # Verificar tunnel
    if ($tunnelProc -and $tunnelProc.HasExited) {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Tunnel caiu! Reiniciando..." -ForegroundColor Yellow
        $tunnelProc = Start-Tunnel
    }

    # Status periodico (a cada 4 checks = ~1 min)
    $script:checkCount = ($script:checkCount ?? 0) + 1
    if ($script:checkCount -ge 4) {
        $script:checkCount = 0
        $dbStatus = if ($serverAlive) { "OK" } else { "FALHA" }
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Status: Servidor=$dbStatus | Tunnel=$(
            if ($tunnelProc -and -not $tunnelProc.HasExited) { 'OK' } else { 'FALHA' }
        )" -ForegroundColor $(if ($serverAlive) { 'DarkGray' } else { 'Red' })
    }
}
