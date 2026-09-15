; Inno Setup script for Nab'd.
;
; Ships everything: the frozen app, ffmpeg, the brand faces and the rendered
; artwork. Nothing is required on the target machine - no Python, no ffmpeg.
;
; Installs per-user (no admin prompt). The app writes to LOCALAPPDATA, so a
; per-user install has everything it needs and friends get no UAC dialog.

#define AppName "Nab'd"
#define AppShortName "Nabd"
#define AppVersion "2.0.0"
#define AppPublisher "Nab'd"
#define AppExe "Nabd.exe"

[Setup]
AppId={{8B5E1A42-6C3B-4AAF-9D2E-4E2A7D0C1F55}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppShortName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=no
OutputDir=dist
OutputBaseFilename=NabdSetup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Inno 6 skips the welcome page by default; this is a program someone
; downloads, so it gets the full Welcome -> Location -> Options -> Install
; -> Finish walkthrough.
DisableWelcomePage=no
WizardImageFile=installer\wizard-*.bmp
WizardSmallImageFile=installer\wizardsmall-*.bmp
; Per-user: no admin, so no UAC prompt for whoever you send it to. No
; all-users override offered - it would only add a dialog before the wizard,
; and Nab'd has nothing to put outside the user profile.
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%nNab'd keeps the last few minutes of your screen and sound in a rolling buffer. Press a key and it writes them out as a video - no account, no overlay, nothing uploaded anywhere.%n%nEverything it needs is included, so there is nothing else to download.%n%nIt is recommended that you close all other applications before continuing.
FinishedLabelNoIcons=Setup has finished installing [name] on your computer.
FinishedLabel=Setup has finished installing [name] on your computer.%n%nNab'd lives in the system tray. Click its icon to open settings, where you can set your hotkey, pick your microphone and choose where nabs are saved.

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; \
    GroupDescription: "Shortcuts:"
Name: "startup"; Description: "Start {#AppName} when I sign in (recommended)"; \
    GroupDescription: "Startup:"

[Files]
Source: "dist\Nabd\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs \
    createallsubdirs
; The brand faces, so the UI gets real Outfit and JetBrains Mono rather than
; the documented system-ui fallback. Each needs its registered name spelled
; out - FontInstall takes no wildcard. Left behind on uninstall because other
; software may have come to rely on them.
Source: "vendor\fonts\Outfit-Regular.ttf"; DestDir: "{autofonts}"; \
    FontInstall: "Outfit"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "vendor\fonts\Outfit-Medium.ttf"; DestDir: "{autofonts}"; \
    FontInstall: "Outfit Medium"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "vendor\fonts\Outfit-SemiBold.ttf"; DestDir: "{autofonts}"; \
    FontInstall: "Outfit SemiBold"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "vendor\fonts\Outfit-Bold.ttf"; DestDir: "{autofonts}"; \
    FontInstall: "Outfit Bold"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "vendor\fonts\JetBrainsMono-Regular.ttf"; DestDir: "{autofonts}"; \
    FontInstall: "JetBrains Mono"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "vendor\fonts\JetBrainsMono-Bold.ttf"; DestDir: "{autofonts}"; \
    FontInstall: "JetBrains Mono Bold"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{#AppName} Settings"; Filename: "{app}\{#AppExe}"; \
    Parameters: "--settings"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; \
    Tasks: desktopicon

[Registry]
; Autostart from the Run key rather than a Startup-folder shortcut. Explorer
; processes Run before the Startup folder, and the nab hotkey is claimed with
; RegisterHotKey, which is first-come-first-served with no way to outrank an
; earlier claimant - starting last meant every overlay and rival clip recorder
; on the machine had already taken its pick of the keys. (A logon scheduled
; task would start earlier still, but creating one needs admin, which would
; cost this installer its no-UAC install.)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "{#AppShortName}"; \
    ValueData: """{app}\{#AppExe}"""; \
    Flags: uninsdeletevalue; Tasks: startup

[InstallDelete]
; Older builds autostarted from the Startup folder; drop it so an upgrade does
; not leave two launches racing each other.
Type: files; Name: "{userstartup}\{#AppName}.lnk"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName} now"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; The rolling buffer can be gigabytes; leaving it behind would be rude.
Type: filesandordirs; Name: "{localappdata}\{#AppShortName}\buffer"
Type: files; Name: "{localappdata}\{#AppShortName}\nabd.log"
Type: files; Name: "{localappdata}\{#AppShortName}\.banner_trigger"

[Code]
// The app and its helpers hold the install folder open; close them before
// writing over the top, and again before removing it.
procedure StopNabd;
var
  Code: Integer;
begin
  Exec(ExpandConstant('{cmd}'),
       '/c taskkill /f /im {#AppExe} >nul 2>&1', '',
       SW_HIDE, ewWaitUntilTerminated, Code);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopNabd;
  Result := '';
end;

function InitializeUninstall: Boolean;
begin
  StopNabd;
  Result := True;
end;
