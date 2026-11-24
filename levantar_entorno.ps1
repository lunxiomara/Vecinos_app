$ErrorActionPreference = "Stop"

Write-Host "=== VecinosApp - Levantando entorno ===" -ForegroundColor Cyan

if (-not (Test-Path "venv\Scripts\Activate.ps1")) {
    Write-Host "Creando entorno virtual venv..." -ForegroundColor Yellow
    python -m venv venv
}

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
& ".\venv\Scripts\Activate.ps1"

if (Test-Path "requirements.txt") {
    Write-Host "Verificando dependencias..." -ForegroundColor Yellow
    pip install -q -r requirements.txt
}

Write-Host "Aplicando migraciones..." -ForegroundColor Yellow
python manage.py migrate

Write-Host "Iniciando servidor Django..." -ForegroundColor Green
python manage.py runserver