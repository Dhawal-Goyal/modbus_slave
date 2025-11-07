\
; Inno Setup installer for Modbus RTU Slave Simulator (GUI + optional CLI)
; Requires Inno Setup 6.x (https://jrsoftware.org/isinfo.php)
#define MyAppName "Modbus RTU Slave Simulator"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Ecozen Tools"
#define MyAppExeName "modbus-sim-gui.exe"

[Setup]
AppId={{0A7D3B5C-9E8E-4C4B-B8B8-5E3C7B6E9D24}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={pf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableDirPage=no
DisableProgramGroupPage=no
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
OutputBaseFilename=ModbusSlaveSetup
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked
Name: "installcli"; Description: "Also install the CLI tool (modbus-sim.exe)"; GroupDescription: "Optional components:"

[Files]
; Required: GUI exe from PyInstaller
Source: "dist\modbus-sim-gui.exe"; DestDir: "{app}"; Flags: ignoreversion
; Optional: CLI exe if built
Source: "dist\modbus-sim.exe"; DestDir: "{app}"; Flags: ignoreversion; Tasks: installcli
; Sample CSV/README
Source: "sample_map.csv"; DestDir: "{app}"; Flags: ignoreversion
Source: "README_DEPLOY.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
