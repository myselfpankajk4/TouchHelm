$ErrorActionPreference='Stop'
[Console]::InputEncoding=New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Windows.Forms,System.Drawing,System.Web.Extensions
Add-Type -Path (Join-Path $PSScriptRoot 'overlay_native.cs') -ReferencedAssemblies System.Windows.Forms,System.Drawing,System.Web.Extensions
[TouchHelmAirHud]::Run()
