; Установщик GyertAI (Inno Setup 6).
; Сборка: ISCC.exe installer\GyertAI.iss
; Требуется готовая папка dist\GyertAI (её создаёт PyInstaller по GyertAI.spec).

#define AppName "GyertAI"
#define AppVersion "1.0"
#define AppPublisher "Gyert Etc."
#define AppExeName "GyertAI.exe"

[Setup]
AppId={{8F3C1E2A-4B77-4C1E-9E3D-0A6B5C7D9F21}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=GyertAI-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}

; Выбор языка интерфейса установщика на первом экране
[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\GyertAI\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Данные пользователя (база памяти, аудио) лежат в %LOCALAPPDATA%\GyertAI
; и при удалении программы намеренно не трогаются.
Type: dirifempty; Name: "{app}"
