# TouchHelm's private Windows bridge. Requests arrive as data, never PowerShell code.
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$script:knownApps = @{}
$script:sessions = @{}
$script:queueItems = @{}
$script:mediaManager = $null
$script:winrtAvailable = $null
$script:appWindows = @{}
$script:windowIds = @{}
$script:iconCache = @{}
$script:slidePreviewCache = @{}
$script:presentationTarget = $null
$script:registrations = $null
$script:registrationsAt = [DateTime]::MinValue

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type -Path (Join-Path $PSScriptRoot 'desktop_native.cs') -ReferencedAssemblies System.Drawing

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
             genre=@(); track=$null; album_tracks=$null; artwork_id=$null;
             status='unavailable'; playback_rate=$null; shuffle=$null; repeat=$null;
             position=$null; duration=$null; min_seek=$null; max_seek=$null;
             updated_at=([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()/1000.0);
             capabilities=(Media-Capabilities $null); message=$message}
}

function Media-Capabilities($controls) {
    $map = @{play='IsPlayEnabled'; pause='IsPauseEnabled'; play_pause='IsPlayPauseToggleEnabled'; next='IsNextEnabled';
             prev='IsPreviousEnabled'; stop='IsStopEnabled'; seek='IsPlaybackPositionEnabled';
             shuffle='IsShuffleEnabled'; repeat='IsRepeatEnabled'; rate='IsPlaybackRateEnabled'}
    $result = @{}
    foreach ($key in $map.Keys) { $result[$key] = [bool]$controls.($map[$key]) }
    return $result
}

function Get-SessionProperties($session) {
    $propertiesType = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties, Windows.Media.Control, ContentType=WindowsRuntime]
    return Await-WinRT ($session.TryGetMediaPropertiesAsync()) $propertiesType
}

function Read-Thumbnail($thumbnail) {
    if ($null -eq $thumbnail) { return $null }
    $stream = $null; $reader = $null
    try {
        $streamType = [Windows.Storage.Streams.IRandomAccessStreamWithContentType, Windows.Storage.Streams, ContentType=WindowsRuntime]
        $stream = Await-WinRT ($thumbnail.OpenReadAsync()) $streamType
        if ($stream.Size -le 0 -or $stream.Size -gt 4194304) { return $null }
        $readerType = [Windows.Storage.Streams.DataReader, Windows.Storage.Streams, ContentType=WindowsRuntime]
        $reader = $readerType::new($stream.GetInputStreamAt(0))
        $count = Await-WinRT ($reader.LoadAsync([uint32]$stream.Size)) ([uint32])
        if ($count -ne $stream.Size) { return $null }
        $bytes = New-Object byte[] $count
        $reader.ReadBytes($bytes)
        return [Convert]::ToBase64String($bytes)
    } catch { return $null }
    finally { if ($null -ne $reader) { $reader.Dispose() }; if ($null -ne $stream) { $stream.Dispose() } }
}

function Read-MediaSession($session, [string]$identifier) {
    $result = Empty-Media ''
    $result.available = $true; $result.session_id = $identifier; $result.id = $identifier
    $result.app = [string]$session.SourceAppUserModelId; $result.status = 'unknown'
    try {
        $properties = Get-SessionProperties $session
        $result.title = [string]$properties.Title
        $result.artist = [string]$properties.Artist
        $result.album = [string]$properties.AlbumTitle
        $result.genre = @($properties.Genres)
        if ($properties.TrackNumber -gt 0) { $result.track = [int]$properties.TrackNumber }
        if ($properties.AlbumTrackCount -gt 0) { $result.album_tracks = [int]$properties.AlbumTrackCount }
        $result.artwork_data = Read-Thumbnail $properties.Thumbnail
    } catch { $result.message = 'This player did not expose complete media metadata.' }
    try {
        $playback = $session.GetPlaybackInfo()
        $result.status = [string]$playback.PlaybackStatus
        $result.capabilities = Media-Capabilities $playback.Controls
        if ($null -ne $playback.PlaybackRate) { $result.playback_rate = [double]$playback.PlaybackRate }
        if ($null -ne $playback.IsShuffleActive) { $result.shuffle = [bool]$playback.IsShuffleActive }
        if ($null -ne $playback.AutoRepeatMode) { $result.repeat = ([string]$playback.AutoRepeatMode).ToLowerInvariant() }
        $timeline = $session.GetTimelineProperties()
        $result.position = [Math]::Max(0, ($timeline.Position - $timeline.StartTime).TotalSeconds)
        $length = ($timeline.EndTime - $timeline.StartTime).TotalSeconds
        if ($length -gt 0) { $result.duration = $length }
        if ($null -ne $timeline.MinSeekTime) { $result.min_seek = [Math]::Max(0, ($timeline.MinSeekTime - $timeline.StartTime).TotalSeconds) }
        if ($null -ne $timeline.MaxSeekTime) { $result.max_seek = [Math]::Max(0, ($timeline.MaxSeekTime - $timeline.StartTime).TotalSeconds) }
        if ($null -ne $timeline.LastUpdatedTime) { $result.updated_at = $timeline.LastUpdatedTime.ToUnixTimeMilliseconds()/1000.0 }
    } catch {
        $result.message = 'This player did not expose complete playback information.'
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
    $identity = @((Get-DesktopWindows) | Where-Object { $_.handle -eq $handle.ToInt64() }) | Select-Object -First 1
    return @{app=[string]$process.ProcessName; title=$text.ToString(); handle=$handle.ToInt64();
             identity=[string]$identity.identity; exe=[string]$identity.exe}
}

function Get-PowerPoint {
    try { return [Runtime.InteropServices.Marshal]::GetActiveObject('PowerPoint.Application') }
    catch { return $null }
}

function Read-Presentation {
    $result = @{available=$false; app=''; title=''; active=$false; slide=$null;
                total=$null; slide_title=''; capabilities=@{details=$false;goto=$false;previews=$false;notes=$false;native_fallback=$false};
                display=$null; message='No supported presentation context is available.'}
    $powerpoint = Get-PowerPoint
    if ($null -ne $powerpoint) {
        try {
            $deck = $powerpoint.ActivePresentation
            $result.available = $true
            $result.app = 'PowerPoint'
            $result.title = [string]$deck.Name
            $result.total = [int]$deck.Slides.Count
            $result.capabilities = @{details=$true;goto=$true;previews=$true;notes=$true;native_fallback=$false}
            $result.message = ''
            $slide = $null
            if ($powerpoint.SlideShowWindows.Count -gt 0) {
                $result.active = $true
                $show = $powerpoint.SlideShowWindows.Item(1)
                $slide = $show.View.Slide
                try { $result.display = Display-ForWindow ([long]$show.HWND) } catch {}
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
        $result.app = $window.app
        $result.title = $window.title
        $result.message = 'Window title only. This window is not verified as a presentation target.'
        if (Test-PresentationWindow $window) {
            $result.available = $true
            $result.capabilities.native_fallback = $true
            $script:presentationTarget = $window
            $result.message = 'Verified document window only. Slide details and slideshow state are unavailable; controls use native shortcuts.'
            if ($window.app -match '^(chrome|msedge|firefox)$') {
                $result.message = 'Browser deck identified by its caption only. Document contents and slide state are not inspected; native shortcuts require this same focused window.'
            }
            $result.display = Display-ForWindow ([long]$window.handle)
        }
    }
    return $result
}

function Test-PresentationWindow($window) {
    if (-not $window.handle -or -not $window.identity) { return $false }
    $pdf = $window.app -match '^(Acrobat|AcroRd32|SumatraPDF|FoxitPDFReader)$' -and $window.title -match '(?i)\.pdf(?:\s|$)'
    # Specific deck captions are an explicit heuristic, not browser DOM access.
    # Never authorize a generic browser window solely from its process name.
    $browser = $window.app -match '^(chrome|msedge|firefox)$' -and
               $window.title -match '(?i) - (Google Slides|PowerPoint(?: for the web)?|Keynote)(?: - (Google Chrome|Microsoft Edge|Mozilla Firefox))?$'
    return $pdf -or $browser
}

function Presentation-Fallback {
    $window = Read-Window
    if ($null -ne $script:presentationTarget -and (Test-PresentationWindow $window) -and
        $window.handle -eq $script:presentationTarget.handle -and $window.identity -eq $script:presentationTarget.identity -and
        $window.title -eq $script:presentationTarget.title) {
        return @{success=$false;handled=$false;message='Verified document window ready for native shortcut.'}
    }
    return @{success=$false;handled=$true;message='Focus the verified presentation document before using its controls.'}
}

function Read-SlideTitle($slide) {
    try { if ($slide.Shapes.HasTitle) { return [string]$slide.Shapes.Title.TextFrame.TextRange.Text } } catch {}
    return ''
}

function Read-SlidePreview($slide, $deck=$null) {
    if ($null -eq $script:slidePreviewCache) { $script:slidePreviewCache = @{} }
    # Short-lived thumbnails avoid exporting the same current/next slide on every
    # drawer open. Unsaved content can change without a slide identity change.
    $now = [DateTime]::UtcNow
    $key = $null
    try {
        $key = [string]$deck.FullName + '|' + [string]$deck.Name + '|' + [string]$slide.SlideID + '|' +
               [string]$slide.Shapes.Count + '|' + [string]$deck.Saved + '|' + (Read-SlideTitle $slide)
        $cached = $script:slidePreviewCache[$key]
        if ($null -ne $cached -and ($now - $cached.created).TotalSeconds -lt 10) { return $cached.data }
    } catch { $key = $null }
    $path = Join-Path ([IO.Path]::GetTempPath()) ('TouchHelm-preview-' + [Guid]::NewGuid().ToString('N') + '.png')
    try {
        $width=960; $height=540
        if ($null -ne $deck -and $deck.PageSetup.SlideWidth -gt 0 -and $deck.PageSetup.SlideHeight -gt 0) {
            $ratio = [double]$deck.PageSetup.SlideHeight / [double]$deck.PageSetup.SlideWidth
            $height = [int][Math]::Round($width * $ratio)
            if ($height -gt 1024) { $height=1024; $width=[int][Math]::Round($height/$ratio) }
            $width=[Math]::Max(1,$width);$height=[Math]::Max(1,$height)
        }
        $slide.Export($path, 'PNG', $width, $height)
        if ((Get-Item -LiteralPath $path).Length -le 4194304) {
            $data = [Convert]::ToBase64String([IO.File]::ReadAllBytes($path))
            if ($null -ne $key) {
                $script:slidePreviewCache[$key] = @{created=$now;data=$data}
                $size = ($script:slidePreviewCache.Values | ForEach-Object {$_.data.Length} | Measure-Object -Sum).Sum
                while ($script:slidePreviewCache.Count -gt 16 -or $size -gt 8388608) {
                    $oldest = $script:slidePreviewCache.GetEnumerator() | Sort-Object {$_.Value.created} | Select-Object -First 1
                    $size -= $oldest.Value.data.Length
                    $script:slidePreviewCache.Remove($oldest.Key)
                }
            }
            return $data
        }
    } catch {} finally { if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force } }
    return $null
}

function Read-PresentationDetails {
    $result = @{available=$false;current=$null;next=$null;notes='';slides=@();
                capabilities=@{goto=$false;previews=$false;notes=$false};message='PowerPoint presentation details are unavailable.'}
    $powerpoint = Get-PowerPoint
    if ($null -eq $powerpoint) { return $result }
    try {
        $deck = $powerpoint.ActivePresentation
        $current = $null
        if ($powerpoint.SlideShowWindows.Count -gt 0) { $current = $powerpoint.SlideShowWindows.Item(1).View.Slide }
        else { try { $current = $powerpoint.ActiveWindow.View.Slide } catch {} }
        $result.available = $true; $result.message = ''
        $result.capabilities.goto = $true
        if ($null -ne $current) {
            $result.current = @{index=[int]$current.SlideIndex; title=(Read-SlideTitle $current); artwork_data=(Read-SlidePreview $current $deck)}
            $result.capabilities.previews = [bool]$result.current.artwork_data
            if ($current.SlideIndex -lt $deck.Slides.Count) {
                $next = $deck.Slides.Item($current.SlideIndex + 1)
                $result.next = @{index=[int]$next.SlideIndex;title=(Read-SlideTitle $next);artwork_data=(Read-SlidePreview $next $deck)}
            }
            try {
                $notes = @()
                foreach ($shape in $current.NotesPage.Shapes) {
                    # Only the notes-body placeholder; omit slide images, dates,
                    # page numbers and other boilerplate from the notes page.
                    if ($shape.HasTextFrame -and $shape.PlaceholderFormat.Type -eq 2) { $notes += [string]$shape.TextFrame.TextRange.Text }
                }
                $result.notes = ($notes -join "`n").Substring(0, [Math]::Min(65536, ($notes -join "`n").Length))
                $result.capabilities.notes = $true
            } catch { $result.message = 'Speaker notes were not exposed by this presentation.' }
        }
        for ($index=1; $index -le [Math]::Min(500, $deck.Slides.Count); $index++) {
            $slide = $deck.Slides.Item($index)
            $result.slides += @{index=$index;title=(Read-SlideTitle $slide)}
        }
        if ($deck.Slides.Count -gt 500) { $result.message = 'Slide navigation is limited to the first 500 slides.' }
    } catch { $result.message = 'PowerPoint details could not be read: ' + $_.Exception.Message }
    return $result
}

function Read-Displays {
    $displays = @()
    foreach ($screen in [System.Windows.Forms.Screen]::AllScreens) {
        $displays += @{id=$screen.DeviceName;name=$screen.DeviceName;primary=[bool]$screen.Primary;
                       rect=@{x=$screen.Bounds.X;y=$screen.Bounds.Y;width=$screen.Bounds.Width;height=$screen.Bounds.Height}}
    }
    $selected = $null
    $powerpoint = Get-PowerPoint
    try { if ($null -ne $powerpoint -and $powerpoint.SlideShowWindows.Count -gt 0) { $selected = Display-ForWindow ([long]$powerpoint.SlideShowWindows.Item(1).HWND) } } catch {}
    if ($null -eq $selected -and $null -ne $script:presentationTarget) { $selected = Display-ForWindow ([long]$script:presentationTarget.handle) }
    return @{displays=@($displays);selected_id=$(if($null -ne $selected){$selected.id}else{$null})}
}

function Display-ForWindow([long]$handle) {
    $monitor = [TouchHelmNative]::MonitorFromWindow([IntPtr]::new($handle), 2)
    $info = New-Object TouchHelmNative+Monitor
    $info.cbSize = [Runtime.InteropServices.Marshal]::SizeOf($info)
    if ([TouchHelmNative]::GetMonitorInfo($monitor,[ref]$info)) {
        return @{id=$info.device;name=$info.device;primary=($info.flags -band 1) -ne 0;
                 rect=@{x=$info.monitor.left;y=$info.monitor.top;width=$info.monitor.right-$info.monitor.left;height=$info.monitor.bottom-$info.monitor.top}}
    }
    return $null
}

function Get-RegisteredApps {
    if ($null -ne $script:registrations -and ([DateTime]::UtcNow - $script:registrationsAt).TotalSeconds -lt 30) { return $script:registrations }
    $shell = New-Object -ComObject Shell.Application
    $folder = $shell.Namespace('shell:AppsFolder')
    $items = @{}
    if ($null -ne $folder) {
        foreach ($item in $folder.Items()) {
            $items[[string]$item.Path] = $item
            try { $aumid = [string]$item.ExtendedProperty('System.AppUserModel.ID'); if ($aumid) { $items[$aumid] = $item } } catch {}
        }
    }
    $apps = @()
    foreach ($app in Get-StartApps | Select-Object -First 2048) {
        $identifier = [string]$app.AppID
        if (-not $identifier -or $identifier.Contains('"') -or $identifier.Contains("`n") -or $identifier.Contains("`r")) { continue }
        $exe = ''
        try {
            $target = [string]$items[$identifier].ExtendedProperty('System.Link.TargetParsingPath')
            if ($target -and $target -match '(?i)\.exe$' -and [IO.Path]::IsPathRooted($target)) { $exe = [IO.Path]::GetFullPath($target) }
        } catch {}
        if (-not $exe -and [IO.Path]::IsPathRooted($identifier) -and $identifier -match '(?i)\.exe$') { $exe = [IO.Path]::GetFullPath($identifier) }
        $apps += @{id=$identifier; name=[string]$app.Name; exe=$exe}
    }
    $script:registrations = $apps
    $script:registrationsAt = [DateTime]::UtcNow
    return $apps
}

function Get-DesktopWindows { return [TouchHelmNative]::Windows() }
function Read-AppIcon([string]$identifier) { return [TouchHelmNative]::ShellIcon($identifier) }
function Focus-DesktopWindow([long]$handle) { return [TouchHelmNative]::Focus($handle) }

function Matches-AppWindow($app, $window) {
    return ($window.aumid -and $window.aumid.Equals([string]$app.id, [StringComparison]::OrdinalIgnoreCase)) -or
           ($app.exe -and $window.exe -and $window.exe.Equals([string]$app.exe, [StringComparison]::OrdinalIgnoreCase))
}

function Read-Apps {
    $script:knownApps = @{}
    $script:appWindows = @{}
    $windows = @(Get-DesktopWindows)
    $apps = @(); $liveIdentities = @{}; $iconReads = 0; $iconsPending = $false
    $registrations = @(Get-RegisteredApps)
    $iconClock = [Diagnostics.Stopwatch]::StartNew()
    foreach ($app in $registrations) {
        $identifier = [string]$app.id
        $verified = @()
        foreach ($window in $windows) {
            if (Matches-AppWindow $app $window) {
                $key = [string]$window.identity
                if (-not $script:windowIds.ContainsKey($key)) { $script:windowIds[$key] = [Guid]::NewGuid().ToString('N') }
                $windowId = $script:windowIds[$key]
                $liveIdentities[$key] = $true
                $script:appWindows[$windowId] = @{app_id=$identifier; window=$window}
                $verified += @{id=$windowId; title=[string]$window.title}
            }
        }
        $script:knownApps[$identifier] = $app
        if (-not $script:iconCache.ContainsKey($identifier)) {
            if ($iconReads -lt 128 -and $iconClock.ElapsedMilliseconds -lt 1000) {
                $script:iconCache[$identifier] = Read-AppIcon $identifier
                $iconReads++
            } else { $iconsPending = $true }
        }
        $apps += @{id=$identifier;name=[string]$app.name;running=($verified.Count -gt 0);windows=@($verified);icon_data=$script:iconCache[$identifier]}
    }
    foreach ($key in @($script:windowIds.Keys)) { if (-not $liveIdentities.ContainsKey($key)) { $script:windowIds.Remove($key) } }
    foreach ($key in @($script:iconCache.Keys)) { if (-not $script:knownApps.ContainsKey($key)) { $script:iconCache.Remove($key) } }
    return @{apps=@($apps);icons_pending=$iconsPending}
}

function App-Action([string]$appId, [string]$action, [string]$windowId) {
    if ($action -ne 'focus' -or -not $script:knownApps.ContainsKey($appId) -or -not $script:appWindows.ContainsKey($windowId)) {
        return @{success=$false;message='Refresh Apps and choose a verified app window.'}
    }
    $entry = $script:appWindows[$windowId]
    $app = $script:knownApps[$appId]
    $current = @((Get-DesktopWindows) | Where-Object { $_.identity -eq $entry.window.identity }) | Select-Object -First 1
    if ($entry.app_id -ne $appId -or $null -eq $current -or -not (Matches-AppWindow $app $current)) {
        return @{success=$false;message='That window is no longer available.'}
    }
    $success = Focus-DesktopWindow ([long]$current.handle)
    return @{success=[bool]$success;message=$(if($success){'Window focused.'}else{'Windows did not allow this window to take focus.'})}
}
function Media-Command([string]$action, [string]$sessionId, $value=$null) {
    if (-not (Initialize-Media)) { return @{success=$false; handled=[bool]$sessionId; message='Windows media-session APIs are unavailable.'} }
    if ($sessionId) {
        if (-not $script:sessions.ContainsKey($sessionId)) { [void](Read-MediaLibrary) }
        $session = $script:sessions[$sessionId]
        if ($null -eq $session) { return @{success=$false; handled=$true; message='This player is no longer available. Refresh the media list.'} }
    } else { $session = $script:mediaManager.GetCurrentSession() }
    if ($null -eq $session) { return @{success=$false; handled=$false; message='No active media session is available.'} }
    $capabilities = Media-Capabilities ($session.GetPlaybackInfo().Controls)
    if (-not $capabilities[$action]) { return @{success=$false;handled=$true;message='This player does not support that action.'} }
    if ($action -in @('seek','rate')) {
        if ($value -is [bool] -or $value -isnot [ValueType] -or [double]::IsNaN([double]$value) -or [double]::IsInfinity([double]$value)) {
            return @{success=$false;handled=$true;message='Invalid media value.'}
        }
    }
    if ($action -eq 'seek') {
        $timeline = $session.GetTimelineProperties()
        $minimum = ($timeline.MinSeekTime - $timeline.StartTime).TotalSeconds
        $maximum = ($timeline.MaxSeekTime - $timeline.StartTime).TotalSeconds
        if ($value -lt $minimum -or $value -gt $maximum) { return @{success=$false;handled=$true;message='Seek is outside the current timeline.'} }
    }
    if ($action -eq 'rate' -and ($value -lt .25 -or $value -gt 4)) { return @{success=$false;handled=$true;message='Playback rate must be between 0.25 and 4.'} }
    if ($action -eq 'shuffle' -and $value -isnot [bool]) { return @{success=$false;handled=$true;message='Shuffle needs a boolean.'} }
    if ($action -eq 'repeat' -and $value -notin @('none','track','list')) { return @{success=$false;handled=$true;message='Invalid repeat mode.'} }
    $operation = switch ($action) {
        'play_pause' { $session.TryTogglePlayPauseAsync() }
        'play' { $session.TryPlayAsync() }
        'pause' { $session.TryPauseAsync() }
        'next' { $session.TrySkipNextAsync() }
        'prev' { $session.TrySkipPreviousAsync() }
        'stop' { $session.TryStopAsync() }
        'seek' { $session.TryChangePlaybackPositionAsync([long]($timeline.StartTime.Ticks + [Math]::Round([double]$value * 10000000))) }
        'shuffle' { $session.TryChangeShuffleActiveAsync([bool]$value) }
        'repeat' { $modeType = [Windows.Media.MediaPlaybackAutoRepeatMode, Windows.Media, ContentType=WindowsRuntime]; $session.TryChangeAutoRepeatModeAsync([Enum]::Parse($modeType, [string]$value, $true)) }
        'rate' { $session.TryChangePlaybackRateAsync([double]$value) }
        default { return @{success=$false; handled=$false; message='Unsupported media action.'} }
    }
    $success = Await-WinRT $operation ([bool])
    return @{success=[bool]$success; handled=$true;
             message=$(if ($success) {'Player command requested.'} else {'This player does not support that action.'})}
}

function Presentation-Command([string]$action, $slideNumber=$null) {
    $powerpoint = Get-PowerPoint
    if ($null -eq $powerpoint) {
        if ($action -eq 'goto') { return @{success=$false;handled=$true;message='Slide navigation requires PowerPoint.'} }
        return Presentation-Fallback
    }
    try {
        $deck = $powerpoint.ActivePresentation
        if ($action -eq 'goto') {
            if ($slideNumber -is [bool] -or $slideNumber -isnot [int] -and $slideNumber -isnot [long] -or $slideNumber -lt 1 -or $slideNumber -gt $deck.Slides.Count) {
                return @{success=$false;handled=$true;message='Slide is outside the current deck.'}
            }
            if ($powerpoint.SlideShowWindows.Count -gt 0) { $powerpoint.SlideShowWindows.Item(1).View.GotoSlide([int]$slideNumber) }
            else { $powerpoint.ActiveWindow.View.GotoSlide([int]$slideNumber) }
        } elseif ($action -in @('start', 'start_current')) {
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
        } else { return @{success=$false; handled=$true; message='No active PowerPoint slideshow.'} }
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
        'media_command' { return Media-Command ([string]$payload.action) ([string]$payload.session_id) $payload.value }
        'media_play' {
            switch ([string]$payload.kind) {
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
        'presentation_command' { return Presentation-Command ([string]$payload.action) $payload.slide }
        'presentation_details' { return Read-PresentationDetails }
        'displays' { return Read-Displays }
        'app_action' { return App-Action ([string]$payload.app_id) ([string]$payload.action) ([string]$payload.window_id) }
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
