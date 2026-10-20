; Inno Setup script for ClearRead Desktop (document.md, section 6.6).
; Build: ISCC.exe installer\clearread.iss  (after PyInstaller has produced dist\ClearRead)
; Nothing here downloads anything: the installer is fully offline.

#define MyAppName "ClearRead"
#define MyAppVersion "1.7.0"
#define MyAppPublisher "SoFzzz"
#define MyAppExeName "ClearRead.exe"

[Setup]
; Fixed AppId: never change it, Windows uses it to recognise upgrades and the uninstaller.
AppId={{3F6B1C7E-8A42-4D5B-9E1A-6C0D2B7F4A91}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
; The user can pick the folder and whether to install per-user or for all users.
DisableDirPage=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
SetupIconFile=..\resources\icons\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
OutputDir=..\dist\installer
OutputBaseFilename=ClearRead-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
WizardStyle=modern

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\ClearRead\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

; The uninstaller only removes what was installed under {app}. User data in
; %APPDATA%\ClearRead (library, glossary) is deliberately left untouched.
