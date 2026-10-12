param([Parameter(Mandatory=$true)][string]$StatusPath)
$ErrorActionPreference = 'Stop'
$feature = 'App.WirelessDisplay.Connect~~~~0.0.1.0'
function Publish-Setup($state, $progress, $message) {
    @{state=$state;progress=$progress;message=$message} | ConvertTo-Json -Compress | Set-Content -LiteralPath $StatusPath -Encoding UTF8
}
try {
    Publish-Setup 'checking' $null 'Checking the Windows optional feature…'
    $cap = Get-WindowsCapability -Online -Name $feature
    if ($cap.State -eq 'Installed') {
        Publish-Setup 'installed' 100 'Wireless Display is already installed. Open the receiver to cast from a compatible phone.'
        exit 0
    }
    $outputPath = $StatusPath + '.stdout'
    $errorPath = $StatusPath + '.stderr'
    Publish-Setup 'installing' $null 'Downloading and installing Wireless Display from Windows Update. This may take a few minutes…'
    $process = Start-Process -FilePath "$env:SystemRoot\System32\dism.exe" -WindowStyle Hidden -PassThru -ArgumentList @('/Online','/English','/Add-Capability',('/CapabilityName:'+$feature),'/NoRestart') -RedirectStandardOutput $outputPath -RedirectStandardError $errorPath
    $process.Handle | Out-Null
    while (!$process.HasExited) {
        $percent = $null
        if (Test-Path -LiteralPath $outputPath) {
            $text = Get-Content -LiteralPath $outputPath -Raw -ErrorAction SilentlyContinue
            if ($text) {
                $matches = [regex]::Matches($text, '(\d{1,3}(?:\.\d+)?)%')
                if ($matches.Count) {$percent = [Math]::Min(99,[int][double]$matches[$matches.Count-1].Groups[1].Value)}
            }
        }
        Publish-Setup 'installing' $percent 'Installing Wireless Display. Keep this PC online; Windows Update supplies the feature.'
        Start-Sleep -Milliseconds 500
        $process.Refresh()
    }
    $process.WaitForExit()
    $code = $process.ExitCode
    if ($code -eq 3010) {Publish-Setup 'restart_required' 100 'Wireless Display was installed. Restart Windows to finish setup.';exit 0}
    if ($code -ne 0) {throw "Windows installation returned code $code. Check Windows Update, internet access, and optional-feature policies, then retry."}
    $cap = Get-WindowsCapability -Online -Name $feature
    if ($cap.State -ne 'Installed') {throw 'Windows did not confirm that Wireless Display is installed.'}
    Publish-Setup 'installed' 100 'Wireless Display is installed. Open the receiver; Miracast-compatible hardware is still required.'
} catch {
    Publish-Setup 'error' $null $_.Exception.Message
    exit 1
}
