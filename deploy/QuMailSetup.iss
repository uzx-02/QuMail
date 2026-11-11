; =====================================================================
; QuMail Secure Desktop Email Client - Inno Setup Installer Script
; Target: Windows 10 / 11 / Server 2019+ (64-bit x64)
; =====================================================================

#define MyAppName "QuMail"
#define MyAppDisplayName "QuMail Secure Email"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "QuMail Project"
#define MyAppURL "https://github.com/uzx-02/QuMail"
#define MyAppExeName "QuMail.exe"
#define SourceDistDir "..\dist\QuMail-App"

[Setup]
AppId={{9F27C72B-4E7B-4B3A-8F12-7B38A3F49A62}
AppName={#MyAppDisplayName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppDisplayName}
AllowNoIcons=yes
LicenseFile=..\LICENSE
OutputDir=..\dist\Installer
OutputBaseFilename=QuMailSetup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

; 64-bit Windows Architecture Requirement
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

; Support both Administrative (Per-Machine) and Non-Administrative (Per-User) Installations
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog commandline

; Uninstall registry settings
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppDisplayName}

; Close running application instances before upgrade
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Dist directory binaries and native providers
Source: "{#SourceDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Default configuration template
Source: "{#SourceDistDir}\resources\qumail.default.json"; DestDir: "{commonappdata}\{#MyAppName}"; Flags: ignoreversion uninsneveruninstall

[Icons]
Name: "{autoprograms}\{#MyAppDisplayName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppDisplayName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppDisplayName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// =====================================================================
// Custom Pascal Scripting for Vault Safety & Safe Uninstall
// =====================================================================

var
  KeepUserDataCheckbox: Boolean;

// Ensure upgrade preserves vault and existing configuration
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

// Uninstall confirmation & data preservation logic
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
  UserResponse: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\QuMail');
    
    // Check if user vault exists
    if DirExists(DataDir) then
    begin
      // Prompt user whether to remove personal encrypted vaults and private keys
      UserResponse := MsgBox(
        'Do you want to retain your personal encrypted vaults, post-quantum private keys, and email index?' + #13#10 + #13#10 +
        'Select YES to preserve your encrypted keys and mail data (Recommended to prevent data loss).' + #13#10 +
        'Select NO only if you want to permanently delete all local keys and vaults.',
        mbConfirmation, MB_YESNO or MB_DEFBUTTON1);
        
      if UserResponse = IDNO then
      begin
        // Double-check confirmation for irreversible cryptographic data destruction
        if MsgBox(
          'WARNING: All local post-quantum private keys and encrypted vaults will be permanently destroyed. Are you absolutely certain?',
          mbCriticalError, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        begin
          DelTree(DataDir, True, True, True);
        end;
      end;
    end;
  end;
end;
