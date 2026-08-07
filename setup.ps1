# FitQuest -- first-run setup for a fresh machine.
#
#   powershell -ExecutionPolicy Bypass -File setup.ps1
#
# Creates the virtual environment, installs dependencies, verifies the install
# against the test suite, and reports what still needs doing by hand. Safe to
# re-run: every step checks its own precondition first.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$py = Join-Path $root "ironquest_env\Scripts\python.exe"

function Step($n, $text) { Write-Host "`n[$n] $text" -ForegroundColor Cyan }
function Ok($text)       { Write-Host "    OK  $text" -ForegroundColor Green }
function Warn($text)     { Write-Host "    !!  $text" -ForegroundColor Yellow }
function Fail($text)     { Write-Host "    XX  $text" -ForegroundColor Red }

Write-Host "FitQuest setup" -ForegroundColor White
Write-Host ("=" * 60)

# --- 1. Python ---------------------------------------------------------------
Step 1 "Checking Python"
try {
    $ver = (& python --version 2>&1) -replace 'Python ', ''
    $maj, $min = $ver.Split('.')[0..1]
    if ([int]$maj -lt 3 -or ([int]$maj -eq 3 -and [int]$min -lt 12)) {
        Fail "Python $ver found. This project needs 3.12 or newer."
        Write-Host "    Install from https://www.python.org/downloads/ and tick 'Add Python to PATH'."
        exit 1
    }
    Ok "Python $ver"
} catch {
    Fail "Python is not on PATH."
    Write-Host "    Install from https://www.python.org/downloads/ and tick 'Add Python to PATH'."
    exit 1
}

# --- 2. Virtual environment --------------------------------------------------
Step 2 "Virtual environment"
if (Test-Path $py) {
    Ok "ironquest_env already exists"
} else {
    Write-Host "    Creating ironquest_env ..."
    & python -m venv ironquest_env
    if (-not (Test-Path $py)) { Fail "Could not create the virtual environment."; exit 1 }
    Ok "created"
}

# --- 3. Dependencies ---------------------------------------------------------
Step 3 "Installing dependencies (several minutes; PyTorch is large)"
& $py -m pip install --upgrade pip --quiet
& $py -m pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) { Fail "pip install failed. Scroll up for the reason."; exit 1 }
Ok "installed"

# --- 4. Model weights --------------------------------------------------------
Step 4 "Model weights"
$poseW = "weights\yolo26n-pose.pt"
$dumbW = "runs\detect\dumbbell_combined_yolo26n\weights\best.pt"
$missing = @()
foreach ($w in @($poseW, $dumbW)) {
    if (Test-Path $w) {
        Ok ("{0}  ({1:N1} MB)" -f $w, ((Get-Item $w).Length / 1MB))
    } else {
        Fail "missing: $w"
        $missing += $w
    }
}
if ($missing.Count -gt 0) {
    Warn "Weights are committed to the repository. If they are missing, the clone"
    Write-Host "    was incomplete -- try: git lfs pull, or re-clone."
}

# --- 5. Test suite -----------------------------------------------------------
Step 5 "Verifying the install"
& $py -m pytest tests\ -q
if ($LASTEXITCODE -ne 0) {
    Fail "Tests failed. Fix this before connecting any hardware --"
    Write-Host "    a software problem here will look like a hardware problem later."
    exit 1
}
Ok "test suite passes"

# --- 6. Wi-Fi configuration --------------------------------------------------
Step 6 "ESP32 Wi-Fi configuration"
$cfg = "firmware\esp32_s3_bno08x_udp\wifi_config.h"
$example = "firmware\esp32_s3_bno08x_udp\wifi_config.example.h"
if (Test-Path $cfg) {
    Ok "wifi_config.h exists"
    if ((Get-Content $cfg -Raw) -match 'YOUR_WIFI_SSID') {
        Warn "still contains the placeholder SSID -- edit it before flashing"
    }
} else {
    Copy-Item $example $cfg
    Ok "created wifi_config.h from the example"
    Warn "EDIT IT: set WIFI_SSID and WIFI_PASSWORD to your phone hotspot"
}

# --- Summary -----------------------------------------------------------------
Write-Host "`n$("=" * 60)"
Write-Host "Software is ready." -ForegroundColor Green
Write-Host @"

Remaining steps, in this order -- each one gives a verifiable result
before the next can hide a failure inside it:

  1. Try it with no hardware at all:
       .\ironquest_env\Scripts\python.exe -m tools.simulate_game_control_stream
     Open the printed URL. The full client should work.

  2. Flash the ESP32 (Arduino IDE, board 'ESP32S3 Dev Module',
     USB CDC On Boot DISABLED, connected via the UART port):
       firmware\esp32_s3_bno08x_udp\esp32_s3_bno08x_udp.ino

  3. Close the Arduino Serial Monitor -- it holds the port, and the
     failure looks exactly like a disconnected board. Then:
       .\ironquest_env\Scripts\python.exe -m ironquest check-esp32 --port auto --seconds 10 --list-ports

  4. Connect this laptop to the phone hotspot. The campus network will
     not carry the telemetry: enterprise authentication the firmware
     does not implement, and no UDP broadcast between clients.

  5. On the watch: enable Broadcast Heart Rate, then open the FitQuest
     Telemetry app. No rebuild needed.

  6. Run everything:
       .\run_ironquest.bat

Full detail: docs/reports section 15, Reproduction and Handover.
"@
