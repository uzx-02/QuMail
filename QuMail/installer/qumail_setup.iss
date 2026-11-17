; =====================================================================
; QuMail 1.0 — Professional Inno Setup Script
; Post-Quantum Secure Corporate Email Client
; Target: Windows x64 (Windows 10 / 11)
; =====================================================================

#define MyAppName "QuMail"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "QuMail Research & Security Team"
#define MyAppURL "https://qumail.org"
#define MyAppExeName "QuMail.exe"
#define MyAppDistDir "..\dist\QuMail-App"
#define MyAppId "{C8E7F3A1-2B4D-4E9A-8F12-7A9D3E5B1C2F}"

[Setup]
; Unique App ID for upgrade / uninstall detection
AppId={{C8E7F3A1-2B4D-4E9A-8F12-7A9D3E5B1C2F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
AppCopyright=Copyright (C) 2026 QuMail Team. All rights reserved.

; Version Info embedded into installer PE header
VersionInfoVersion=1.0.0.0
VersionInfoProductVersion=1.0.0.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=QuMail Secure Email Client Setup
VersionInfoCopyright=Copyright (C) 2026 QuMail Team.

; Running instance detection and graceful closing
AppMutex=QuMail_SingleInstance_Mutex
SetupMutex=QuMail_Setup_Instance_Mutex
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartApplications=no

; Modern per-user install (No UAC Administrator elevation required)
; Installs into %LocalAppData%\Programs\QuMail like Chrome, VS Code, Slack
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; In-place upgrade detection: automatically reuse existing app directory
UsePreviousAppDir=yes
DisableDirPage=auto

; Output settings
OutputDir=..\dist\Installer
OutputBaseFilename=Setup-QuMail-v1.0
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Modern Visual Styling & Professional Branding
WizardStyle=modern
DisableWelcomePage=no
PrivilegesRequired=lowest
SetupIconFile=qumail.ico
WizardImageFile=wizard_large.bmp
WizardSmallImageFile=wizard_small.bmp

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
SetupWindowTitle=Setup - %1 (Post-Quantum Secure)
WelcomeLabel1=Welcome to [name] Setup
WelcomeLabel2=This wizard will install [name] on your computer.%n%nQuMail delivers ML-KEM / Falcon post-quantum corporate email encryption with hardware security verification and zero-trust identity.%n%nClick Next to continue.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Copy the complete one-directory PyInstaller bundle. In particular, bin/
; contains the integrity-checked native vault provider required at startup.
Source: "{#MyAppDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Classes\qumail"; ValueType: string; ValueName: ""; ValueData: "URL:QuMail Protocol"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\qumail"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\qumail\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Flags: uninsdeletekey

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up runtime caches but strictly preserve user vault in %APPDATA%\QuMail
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\*.log"

[Code]
var
  IsUpgradeMode: Boolean;
  ExistingVersion: String;

// Query Windows Registry to detect existing installation
function DetectExistingInstallation(): Boolean;
var
  UninstallKey: String;
  VerStr: String;
begin
  UninstallKey := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppId}_is1';
  Result := False;
  ExistingVersion := '';
  
  if RegQueryStringValue(HKCU, UninstallKey, 'DisplayVersion', VerStr) then
  begin
    ExistingVersion := VerStr;
    Result := True;
  end;
end;

function InitializeSetup(): Boolean;
begin
  IsUpgradeMode := DetectExistingInstallation();
  Result := True;
end;

procedure InitializeWizard();
begin
  if IsUpgradeMode then
  begin
    WizardForm.Caption := 'Setup - QuMail (Update Mode)';
    WizardForm.WelcomeLabel1.Caption := 'Updating QuMail';
    if ExistingVersion <> '' then
    begin
      WizardForm.WelcomeLabel2.Caption := 
        'Setup has detected an existing installation of QuMail (v' + ExistingVersion + ') on this system.' + #13#10 + #13#10 +
        'This wizard will upgrade your installation in place to version {#MyAppVersion}.' + #13#10 + #13#10 +
        'Your local encrypted mailbox databases, post-quantum private keys, contacts, and custom preferences will remain completely safe and intact.' + #13#10 + #13#10 +
        'Click Update to proceed with the upgrade.';
    end
    else
    begin
      WizardForm.WelcomeLabel2.Caption := 
        'Setup has detected an existing installation of QuMail on this system.' + #13#10 + #13#10 +
        'This wizard will safely upgrade your installation to version {#MyAppVersion}.' + #13#10 + #13#10 +
        'Your local encrypted mailbox databases, post-quantum private keys, and preferences will be preserved.' + #13#10 + #13#10 +
        'Click Update to proceed.';
    end;
    WizardForm.NextButton.Caption := '&Update';
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpFinished) and IsUpgradeMode then
  begin
    WizardForm.FinishedHeadingLabel.Caption := 'QuMail Update Complete';
    WizardForm.FinishedLabel.Caption := 
      'QuMail has been successfully updated to version {#MyAppVersion}.' + #13#10 + #13#10 +
      'Click Finish to exit Setup and launch QuMail.';
  end;
end;
