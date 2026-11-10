; =====================================================================
; QuMail 1.0 — Inno Setup Script
; Post-Quantum Secure Corporate Email Client
; Target: Windows x64 (Windows 10 / 11)
; =====================================================================

#define MyAppName "QuMail"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "QuMail Research & Security Team"
#define MyAppURL "https://qumail.org"
#define MyAppExeName "QuMail.exe"
#define MyAppDistDir "..\dist\QuMail"

[Setup]
; Unique App ID for upgrade / uninstall detection
AppId={{C8E7F3A1-2B4D-4E9A-8F12-7A9D3E5B1C2F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Modern per-user install (No UAC Administrator elevation required)
; Installs into %LocalAppData%\Programs\QuMail like Chrome, VS Code, Slack
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; Output settings
OutputDir=..\dist\installer
OutputBaseFilename=Setup-QuMail-v1.0
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; UI and Appearance
WizardStyle=modern
DisableWelcomePage=no
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Primary PyInstaller binary and internal dependencies
Source: "{#MyAppDistDir}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#MyAppDistDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#MyAppDistDir}\resources\*"; DestDir: "{app}\resources"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#MyAppDistDir}\version.json"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up runtime caches but strictly preserve user vault in %APPDATA%\QuMail
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\*.log"

[Code]
// Custom Inno Setup Pascal Script to check and preserve user vault
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
