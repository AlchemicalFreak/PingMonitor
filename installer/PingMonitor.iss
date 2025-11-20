; Inno Setup installer for PingMonitor

#define MyAppName "PingMonitor"
#define MyAppVersion "1.0.2"
#define MyAppPublisher "LutsykOV"
#define MyAppExeName "PingMonitor.exe"

[Setup]
AppId={{7A80AE61-2BB8-4914-81CC-29609DACCEEC}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}

ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes

OutputDir=D:\CODE\PingMonitor\installer
OutputBaseFilename=PingMonitorSetup
SetupIconFile=D:\CODE\PingMonitor\icon.ico
SolidCompression=yes
WizardStyle=modern dynamic

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Запускати PingMonitor при старті Windows"; Flags: unchecked

[Files]
Source: "D:\CODE\PingMonitor\dist\PingMonitor.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\CODE\PingMonitor\dist\icon.ico"; DestDir: "{app}"; Flags: ignoreversion

; ДОДАТКОВІ ІКОНКИ
Source: "D:\CODE\PingMonitor\dist\telegram.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\CODE\PingMonitor\dist\lighttheme.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\CODE\PingMonitor\dist\darktheme.ico"; DestDir: "{app}"; Flags: ignoreversion

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустити PingMonitor"; Flags: nowait postinstall skipifsilent

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "PingMonitor"; ValueData: """{app}\{#MyAppExeName}"""; \
    Tasks: autostart
