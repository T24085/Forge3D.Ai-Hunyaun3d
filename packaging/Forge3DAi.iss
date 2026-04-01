#define AppName "Forge3D.Ai"
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#define Publisher "Forge3D.Ai"
#define ExeName "Forge3DAi.exe"
#define SourceDir "..\\dist\\Forge3DAi"

[Setup]
AppId={{FBD8E80D-CB80-4B58-A7DA-8D18F2A8ECA6}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#Publisher}
DefaultDirName={autopf}\Forge3DAi
DefaultGroupName=Forge3D.Ai
UninstallDisplayIcon={app}\{#ExeName}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
OutputDir=..\dist
OutputBaseFilename=Forge3DAi-Setup
SetupIconFile=..\assets\forge3d-icon.ico

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Forge3D.Ai"; Filename: "{app}\{#ExeName}"; IconFilename: "{app}\assets\forge3d-icon.ico"
Name: "{autodesktop}\Forge3D.Ai"; Filename: "{app}\{#ExeName}"; Tasks: desktopicon; IconFilename: "{app}\assets\forge3d-icon.ico"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\{#ExeName}"; Description: "Launch Forge3D.Ai"; Flags: nowait postinstall skipifsilent
