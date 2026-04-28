; NetLens Inno Setup Script
; Compila con: ISCC.exe installer\NetLens.iss

#define MyAppName "NetLens"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "SW2"
#define MyAppExeName "NetLens.exe"

[Setup]
AppId={{B2B23E5D-48C8-4A2B-9DA6-41B6347C0B01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=NetLens_Setup
Compression=lzma
SolidCompression=yes
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\\Spanish.isl"

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el Escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Ejecutar {#MyAppName}"; Flags: nowait postinstall skipifsilent
