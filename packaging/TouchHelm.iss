; Compile using build_installer.py. Requires Inno Setup 6.7 or newer.
#ifndef StageDir
  #error StageDir is required
#endif
#ifndef OutputDir
  #error OutputDir is required
#endif
#ifndef OutputName
  #define OutputName "TouchHelm-2.2.3-setup-win-x64"
#endif

[Setup]
AppId={{35ADAE35-C8FB-4D10-BCE5-964D4C96BE66}
AppName=TouchHelm
AppVersion=2.2.3
AppVerName=TouchHelm 2.2.3
AppPublisher=TouchHelm Project
AppPublisherURL=https://github.com/myselfpankajk4/TouchHelm
VersionInfoVersion=2.2.3.0
VersionInfoDescription=TouchHelm Windows Setup
DefaultDirName={localappdata}\Programs\TouchHelm
DefaultGroupName=TouchHelm
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0
WizardStyle=modern
SetupIconFile=..\assets\touchhelm.ico
UninstallDisplayIcon={app}\TouchHelm.exe
UninstallDisplayName=TouchHelm
OutputDir={#OutputDir}
OutputBaseFilename={#OutputName}
Compression=lzma2/ultra64
SolidCompression=yes
LZMANumBlockThreads=1
LZMAUseSeparateProcess=yes
CloseApplications=yes
RestartApplications=no
ChangesEnvironment=no
SetupLogging=yes
AppMutex=Local\TouchHelm.Desktop

[Messages]
SetupAppRunningError=TouchHelm is running. Choose Exit from its tray menu, then retry setup.
UninstallAppRunningError=TouchHelm is running. Choose Exit from its tray menu, then retry uninstall.

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: checkedonce

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: files; Name: "{app}\app\web\theme-effects.css"
Type: files; Name: "{app}\app\web\theme-effects.js"
Type: files; Name: "{app}\app\web\themes\clay.css"
Type: files; Name: "{app}\app\web\themes\companion.css"
Type: files; Name: "{app}\app\web\themes\glass.css"
Type: files; Name: "{app}\app\web\themes\soft.css"
Type: filesandordirs; Name: "{app}\app\web\themes\assets"
Type: filesandordirs; Name: "{app}\app\assets\theme"

[Icons]
Name: "{userprograms}\TouchHelm"; Filename: "{app}\TouchHelm.exe"; WorkingDir: "{app}"; AppUserModelID: "TouchHelm.Desktop"
Name: "{userdesktop}\TouchHelm"; Filename: "{app}\TouchHelm.exe"; WorkingDir: "{app}"; Tasks: desktopicon; AppUserModelID: "TouchHelm.Desktop"

[Run]
Filename: "{app}\TouchHelm.exe"; Description: "Open TouchHelm"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ExitCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    WizardForm.StatusLabel.Caption := 'Preparing TouchHelm for this PC...';
    WizardForm.FilenameLabel.Caption := 'Checking the Windows browser runtime';
    if not Exec(ExpandConstant('{app}\TouchHelm.exe'), '--prepare-only',
      ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ExitCode) then
      RaiseException('Windows could not prepare TouchHelm. Run TouchHelm Setup again to repair it.');
    if ExitCode <> 0 then
      RaiseException('TouchHelm files are installed, but Windows browser setup did not finish. Check internet access and open TouchHelm to retry automatically.');
  end;
end;
