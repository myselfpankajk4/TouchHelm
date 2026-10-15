param([switch]$BridgeHost)
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$references = @([System.Windows.Automation.AutomationElement].Assembly.Location,
    [System.Windows.Automation.AutomationPattern].Assembly.Location, 'WindowsBase', 'System', 'System.Core')
Add-Type -Path (Join-Path $PSScriptRoot 'text_native.cs') -ReferencedAssemblies $references
if ($BridgeHost) { [Console]::WriteLine('{"ready":true}') }
while ($null -ne ($line = [Console]::ReadLine())) {
    $identifier = $null
    try {
        $request = ConvertFrom-Json $line
        $identifier = $request.id
        if ($request.command -eq 'read') { $result = [TouchHelmFocusedText]::Read() }
        elseif ($request.command -eq 'write') {
            $p = $request.payload
            $result = [TouchHelmFocusedText]::Write([string]$p.field_id, [string]$p.revision, [string]$p.text, [string]$p.newline_mode)
        } else { throw 'Unsupported request' }
        $response = @{id=$identifier; result=$result}
    } catch {
        # UI Automation provider errors may contain app contents; never return them.
        $response = @{id=$identifier; result=@{available=$false; message='The focused app does not expose editable text. Native typing remains available.'}}
    }
    [Console]::WriteLine((ConvertTo-Json -InputObject $response -Depth 5 -Compress))
}
