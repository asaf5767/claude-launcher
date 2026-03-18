# Claude Launcher - Setup Helper
# Run this once to add the 'cl' command to your PATH

$ScriptsDir = (python -c "import site; print(site.getusersitepackages().replace('site-packages', 'Scripts'))") 2>$null
if (-not $ScriptsDir) {
    $ScriptsDir = (python -c "import sysconfig; print(sysconfig.get_path('scripts', 'nt_user'))")
}

Write-Host ""
Write-Host "  Claude Launcher Setup" -ForegroundColor Magenta
Write-Host "  =====================" -ForegroundColor Magenta
Write-Host ""

# Check if already on PATH
$currentPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($currentPath -like "*$ScriptsDir*") {
    Write-Host "  [OK] Python Scripts directory is already on your PATH" -ForegroundColor Green
    Write-Host "  Directory: $ScriptsDir" -ForegroundColor Gray
} else {
    Write-Host "  Adding Python Scripts directory to your user PATH..." -ForegroundColor Yellow
    Write-Host "  Directory: $ScriptsDir" -ForegroundColor Gray

    [Environment]::SetEnvironmentVariable(
        "PATH",
        "$currentPath;$ScriptsDir",
        "User"
    )
    Write-Host "  [OK] Added to PATH. Restart your terminal for changes to take effect." -ForegroundColor Green
}

Write-Host ""
Write-Host "  Usage:" -ForegroundColor Cyan
Write-Host "    cl                    # Launch the TUI picker" -ForegroundColor White
Write-Host "    claude-launcher       # Same thing, longer name" -ForegroundColor White
Write-Host "    python -m claude_launcher  # Always works" -ForegroundColor White
Write-Host ""

# Also create a PowerShell alias in profile
$ProfileDir = Split-Path $PROFILE
if (-not (Test-Path $ProfileDir)) {
    New-Item -ItemType Directory -Path $ProfileDir -Force | Out-Null
}

$AliasLine = "function cl { python -m claude_launcher @args }"
$ProfileContent = ""
if (Test-Path $PROFILE) {
    $ProfileContent = Get-Content $PROFILE -Raw
}

if ($ProfileContent -notlike "*function cl*claude_launcher*") {
    Add-Content -Path $PROFILE -Value "`n# Claude Launcher - quick access`n$AliasLine`n"
    Write-Host "  [OK] Added 'cl' function to your PowerShell profile ($PROFILE)" -ForegroundColor Green
} else {
    Write-Host "  [OK] 'cl' function already in your PowerShell profile" -ForegroundColor Green
}

Write-Host ""
Write-Host "  All done! Open a new terminal and type 'cl' to launch." -ForegroundColor Green
Write-Host ""
