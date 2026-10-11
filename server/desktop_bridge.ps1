# TouchHelm's private Windows bridge. Requests arrive as data, never PowerShell code.
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$script:knownApps = @{}
$script:sessions = @{}
$script:queueItems = @{}
$script:mediaManager = $null
$script:winrtAvailable = $null

Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class TouchHelmWindowContext {
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int count);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint processId);
}
'@

function Await-WinRT($operation, [Type]$resultType) {
    $method = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetGenericArguments().Length -eq 1 -and
        $_.GetParameters().Length -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    } | Select-Object -First 1
    if ($null -eq $method) { throw 'Windows Runtime async adapter unavailable.' }
    $task = $method.MakeGenericMethod($resultType).Invoke($null, [object[]]@($operation))
    if (-not $task.Wait(2500)) { throw 'Windows Runtime operation timed out.' }
    return $task.Result
}

function Initialize-Media {
    if ($script:winrtAvailable -eq $false) { return $false }
    try {
        if ($null -eq $script:mediaManager) {
            Add-Type -AssemblyName System.Runtime.WindowsRuntime
            $managerType = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType=WindowsRuntime]
            $script:mediaManager = Await-WinRT ($managerType::RequestAsync()) $managerType
        }
        $script:winrtAvailable = $true
        return $true
    } catch {
        $script:winrtAvailable = $false
        return $false
    }
}

function Empty-Media([string]$message) {
    return @{available=$false; session_id=''; app=''; title=''; artist=''; album='';
             status='unavailable'; position=$null; duration=$null; message=$message}
}

function Read-MediaSession($session, [string]$identifier) {
    $result = @{available=$true; session_id=$identifier; id=$identifier;
                app=[string]$session.SourceAppUserModelId; title=''; artist=''; album='';
                status='unknown'; position=$null; duration=$null; message=''}
    try {
        $propertiesType = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties, Windows.Media.Control, ContentType=WindowsRuntime]
        $properties = Await-WinRT ($session.TryGetMediaPropertiesAsync()) $propertiesType
        $result.title = [string]$properties.Title
        $result.artist = [string]$properties.Artist
        $result.album = [string]$properties.AlbumTitle
        $result.status = [string]$session.GetPlaybackInfo().PlaybackStatus
        $timeline = $session.GetTimelineProperties()
        $result.position = [Math]::Max(0, ($timeline.Position - $timeline.StartTime).TotalSeconds)
        $length = ($timeline.EndTime - $timeline.StartTime).TotalSeconds
        if ($length -gt 0) { $result.duration = $length }
    } catch {
        $result.message = 'This player did not expose complete playback metadata.'
    }
    return $result
}

function Get-ActiveMediaPlayer {
    try { return [Runtime.InteropServices.Marshal]::GetActiveObject('WMPlayer.OCX') }
    catch { return $null }
}

function Get-SessionIdentity($session) {
    $unknown = [Runtime.InteropServices.Marshal]::GetIUnknownForObject($session)
    try { return [string]$session.SourceAppUserModelId + ':' + $unknown.ToInt64().ToString('x') }
    finally { [void][Runtime.InteropServices.Marshal]::Release($unknown) }
}

function Get-QueueIdentity($track) {
    $source = [string]$track.sourceURL + "`0" + [string]$track.name
    $hash = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = $hash.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($source))
        return 'queue:' + ([BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()).Substring(0, 24)
    } finally { $hash.Dispose() }
}

function Read-MediaLibrary {
    $script:sessions = @{}
    $script:queueItems = @{}
    $sessionResults = @()
    $current = Empty-Media 'No active Windows media session is available.'
    if (Initialize-Media) {
        $currentSession = $script:mediaManager.GetCurrentSession()
        $currentIdentity = ''
        if ($null -ne $currentSession) { $currentIdentity = Get-SessionIdentity $currentSession }
        foreach ($session in $script:mediaManager.GetSessions()) {
            $identifier = Get-SessionIdentity $session
            $script:sessions[$identifier] = $session
            $state = Read-MediaSession $session $identifier
            $sessionResults += $state
            if ($identifier -eq $currentIdentity) {
                $current = $state
            }
        }
    } else {
        $current = Empty-Media 'Windows media-session APIs are unavailable on this Windows version.'
    }
    $items = @()
    $supported = $false
    $message = 'Windows media sessions do not expose player queues.'
    # Windows Media Player exposes its real currentPlaylist through COM when
    # a running instance registers that object. Never instantiate a player.
    try {
        $player = Get-ActiveMediaPlayer
        $playlist = $player.currentPlaylist
        if ($null -ne $playlist) {
            $supported = $true
            $message = 'Current playlist exposed by Windows Media Player.'
            $limit = [Math]::Min(200, [int]$playlist.count)
            for ($index=0; $index -lt $limit; $index++) {
                $track = $playlist.Item($index)
                $identifier = Get-QueueIdentity $track
                $script:queueItems[$identifier] = @{player=$player; track=$track}
                $items += @{id=$identifier; title=[string]$track.name;
                            subtitle=[string]$track.getItemInfo('Author'); kind='queue'}
            }
        }
    } catch {}
    return @{sessions=@($sessionResults); items=@($items); playlist_supported=$supported;
             playlist_message=$message; current=$current}
}

function Read-Window {
    $handle = [TouchHelmWindowContext]::GetForegroundWindow()
    $text = [System.Text.StringBuilder]::new(1024)
    [void][TouchHelmWindowContext]::GetWindowText($handle, $text, $text.Capacity)
    [uint32]$windowProcess = 0
    [void][TouchHelmWindowContext]::GetWindowThreadProcessId($handle, [ref]$windowProcess)
    $process = Get-Process -Id $windowProcess -ErrorAction SilentlyContinue
    return @{app=[string]$process.ProcessName; title=$text.ToString()}
}

function Get-PowerPoint {
    try { return [Runtime.InteropServices.Marshal]::GetActiveObject('PowerPoint.Application') }
    catch { return $null }
}

function Read-Presentation {
    $result = @{available=$false; app=''; title=''; active=$false; slide=$null;
                total=$null; slide_title=''; message='No supported presentation context is available.'}
    $powerpoint = Get-PowerPoint
    if ($null -ne $powerpoint) {
        try {
            $deck = $powerpoint.ActivePresentation
            $result.available = $true
            $result.app = 'PowerPoint'
            $result.title = [string]$deck.Name
            $result.total = [int]$deck.Slides.Count
            $result.message = ''
            $slide = $null
            if ($powerpoint.SlideShowWindows.Count -gt 0) {
                $result.active = $true
                $slide = $powerpoint.SlideShowWindows.Item(1).View.Slide
            } else {
                try { $slide = $powerpoint.ActiveWindow.View.Slide } catch {}
            }
            if ($null -ne $slide) {
                $result.slide = [int]$slide.SlideIndex
                if ($slide.Shapes.HasTitle) { $result.slide_title = [string]$slide.Shapes.Title.TextFrame.TextRange.Text }
            }
            return $result
        } catch { $result.message = 'PowerPoint is open but its active presentation is unavailable.' }
    }
    $window = Read-Window
    if ($window.app -match '^(POWERPNT|Acrobat|AcroRd32|SumatraPDF|FoxitPDFReader|chrome|msedge|firefox)$') {
        $result.available = $true
        $result.app = $window.app
        $result.title = $window.title
        $result.message = 'Window context only. Slide details and slideshow state are not exposed; controls use native shortcuts.'
    }
    return $result
}

function Read-Apps {
    $script:knownApps = @{}
    $windows = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 })
    $apps = @()
    foreach ($app in Get-StartApps) {
        $identifier = [string]$app.AppID
        if (-not $identifier -or $identifier.Contains('"') -or $identifier.Contains("`n") -or $identifier.Contains("`r")) { continue }
        $name = [string]$app.Name
        $running = $false
        foreach ($process in $windows) {
            if ($process.MainWindowTitle.IndexOf($name, [StringComparison]::OrdinalIgnoreCase) -ge 0 -or
                $name.Equals($process.ProcessName, [StringComparison]::OrdinalIgnoreCase)) {
                $running = $true
                break
            }
        }
        $script:knownApps[$identifier] = $true
        $apps += @{id=$identifier; name=$name; running=$running}
    }
    return @{apps=@($apps)}
}

function Media-Command([string]$action, [string]$sessionId) {
    if (-not (Initialize-Media)) { return @{success=$false; handled=$false; message='Windows media-session APIs are unavailable.'} }
    if ($sessionId) {
        if (-not $script:sessions.ContainsKey($sessionId)) { [void](Read-MediaLibrary) }
        $session = $script:sessions[$sessionId]
        if ($null -eq $session) { return @{success=$false; handled=$true; message='This player is no longer available. Refresh the media list.'} }
    } else { $session = $script:mediaManager.GetCurrentSession() }
    if ($null -eq $session) { return @{success=$false; handled=$false; message='No active media session is available.'} }
    $operation = switch ($action) {
        'play_pause' { $session.TryTogglePlayPauseAsync() }
        'play' { $session.TryPlayAsync() }
        'pause' { $session.TryPauseAsync() }
        'next' { $session.TrySkipNextAsync() }
        'prev' { $session.TrySkipPreviousAsync() }
        'stop' { $session.TryStopAsync() }
        default { return @{success=$false; handled=$false; message='Unsupported media action.'} }
    }
    $success = Await-WinRT $operation ([bool])
    return @{success=[bool]$success; handled=$true;
             message=$(if ($success) {'Player command requested.'} else {'This player does not support that action.'})}
}

function Presentation-Command([string]$action) {
    $powerpoint = Get-PowerPoint
    if ($null -eq $powerpoint) { return @{success=$false; handled=$false; message='Direct PowerPoint control is unavailable; use native presenter shortcuts.'} }
    try {
        $deck = $powerpoint.ActivePresentation
        if ($action -in @('start', 'start_current')) {
            $settings = $deck.SlideShowSettings
            $previousStart = $settings.StartingSlide
            try {
                if ($action -eq 'start_current') { $settings.StartingSlide = $powerpoint.ActiveWindow.View.Slide.SlideIndex }
                else { $settings.StartingSlide = 1 }
                [void]$settings.Run()
            } finally { $settings.StartingSlide = $previousStart }
        } elseif ($powerpoint.SlideShowWindows.Count -gt 0) {
            $view = $powerpoint.SlideShowWindows.Item(1).View
            switch ($action) {
                'next' { $view.Next() }
                'prev' { $view.Previous() }
                'end' { $view.Exit() }
                'black' { $view.State = $(if ($view.State -eq 3) {1} else {3}) }
                'white' { $view.State = $(if ($view.State -eq 4) {1} else {4}) }
                default { return @{success=$false; handled=$false; message='Unsupported presentation action.'} }
            }
        } else { return @{success=$false; handled=$false; message='No active PowerPoint slideshow. Native shortcuts remain available.'} }
        return @{success=$true; handled=$true; message='PowerPoint command requested.'}
    } catch { return @{success=$false; handled=$true; message='PowerPoint could not execute this command: ' + $_.Exception.Message} }
}

function Dispatch-Request($request) {
    $payload = $request.payload
    switch ([string]$request.command) {
        'snapshot' {
            $library = Read-MediaLibrary
            # Current is also an entry in sessions; attach the list to a copy
            # so JSON metadata never contains a recursive session reference.
            $current = $library.current.Clone()
            $current.sessions = @($library.sessions)
            return @{presentation=(Read-Presentation); media=$current}
        }
        'apps' { return Read-Apps }
        'launch_app' {
            $identifier = [string]$payload.app_id
            if (-not $script:knownApps.ContainsKey($identifier)) { [void](Read-Apps) }
            if (-not $script:knownApps.ContainsKey($identifier)) { return @{success=$false; message='App is not registered in the Windows catalog.'} }
            Start-Process -FilePath 'explorer.exe' -ArgumentList ('"shell:AppsFolder\{0}"' -f $identifier)
            return @{success=$true; message='App launch requested.'}
        }
        'media_library' { return Read-MediaLibrary }
        'media_command' { return Media-Command ([string]$payload.action) ([string]$payload.session_id) }
        'media_play' {
            switch ([string]$payload.kind) {
                'local' {
                    $path = [string]$payload.path
                    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return @{success=$false; handled=$true; message='This local media file is no longer available.'} }
                    Start-Process -FilePath $path
                    return @{success=$true; handled=$true; message='Local media opened in its Windows default player.'}
                }
                'session' { return Media-Command 'play' ([string]$payload.session_id) }
                'queue' {
                    $identifier = [string]$payload.item_id
                    if (-not $script:queueItems.ContainsKey($identifier)) { return @{success=$false; handled=$true; message='Playlist changed. Refresh the media list.'} }
                    $entry = $script:queueItems[$identifier]
                    $entry.player.controls.playItem($entry.track)
                    return @{success=$true; handled=$true; message='Playlist item requested.'}
                }
                default { return @{success=$false; handled=$true; message='Unknown media item.'} }
            }
        }
        'presentation_command' { return Presentation-Command ([string]$payload.action) }
        default { throw 'Unknown desktop provider command.' }
    }
}

while ($null -ne ($line = [Console]::ReadLine())) {
    if (-not $line) { continue }
    $identifier = $null
    try {
        $request = ConvertFrom-Json -InputObject $line
        $identifier = $request.id
        $result = Dispatch-Request $request
        $response = @{id=$identifier; result=$result}
    } catch {
        $response = @{id=$identifier; error=$_.Exception.Message}
    }
    [Console]::WriteLine((ConvertTo-Json -InputObject $response -Depth 12 -Compress))
}
