# install_intel_root_ca.ps1
# Fetches the root CA certificate from host.xcopilot.intel.com and installs it
# to the Local Machine Trusted Root store.
# Requires: Run as Administrator

param(
    [string]$Server = "host.xcopilot.intel.com",
    [int]$Port = 443,
    [string]$CertOutput = "$env:TEMP\intel_root_ca.cer"
)

Write-Host ""
Write-Host "  Intel Root CA Installer" -ForegroundColor Cyan
Write-Host "  =======================" -ForegroundColor Cyan
Write-Host ""

# Check admin privileges
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[ERROR] This script must be run as Administrator." -ForegroundColor Red
    Write-Host "        Right-click PowerShell -> 'Run as administrator'" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Connecting to $Server`:$Port ..."

try {
    # Bypass validation to connect and retrieve the certificate chain
    $tcp = New-Object System.Net.Sockets.TcpClient($Server, $Port)
    $ssl = New-Object System.Net.Security.SslStream($tcp.GetStream(), $false, { $true })
    $ssl.AuthenticateAsClient($Server)

    $remoteCert = [System.Security.Cryptography.X509Certificates.X509Certificate2]$ssl.RemoteCertificate
    $chain = New-Object System.Security.Cryptography.X509Certificates.X509Chain
    $chain.Build($remoteCert) | Out-Null

    $ssl.Close()
    $tcp.Close()
} catch {
    Write-Host "[ERROR] Failed to connect to $Server`:$Port" -ForegroundColor Red
    Write-Host "        $_" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Extract root CA (last element in chain)
$root = $chain.ChainElements[$chain.ChainElements.Count - 1].Certificate
Write-Host "[OK] Root CA found: $($root.Subject)" -ForegroundColor Green
Write-Host "     Thumbprint:    $($root.Thumbprint)"

# Check if already installed
$existingStore = New-Object System.Security.Cryptography.X509Certificates.X509Store("Root", "LocalMachine")
$existingStore.Open("ReadOnly")
$existing = $existingStore.Certificates | Where-Object { $_.Thumbprint -eq $root.Thumbprint }
$existingStore.Close()

if ($existing) {
    Write-Host ""
    Write-Host "[SKIP] Certificate already installed in Trusted Root store." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 0
}

# Save to temp file
[System.IO.File]::WriteAllBytes($CertOutput, $root.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert))
Write-Host "[OK] Saved to $CertOutput" -ForegroundColor Green

# Install to Local Machine Trusted Root
Write-Host "Installing to LocalMachine\Root ..."
$result = certutil -addstore -f "ROOT" $CertOutput 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Certificate installed successfully." -ForegroundColor Green
    Remove-Item $CertOutput -Force -ErrorAction SilentlyContinue
} else {
    Write-Host "[ERROR] certutil failed:" -ForegroundColor Red
    Write-Host $result -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "  Done! Agent should now be able to connect to $Server." -ForegroundColor Cyan
Write-Host "  Restart the Agent service to take effect." -ForegroundColor Gray
Write-Host ""
Read-Host "Press Enter to close"
