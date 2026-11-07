; FaceGuard AI Desktop — instalador de Windows (Inno Setup 6)
; Lo compila GitHub Actions (.github/workflows/release.yml):
;   iscc /DAppVersion=1.1.0 /DSourceDir=build\dist\FaceGuardAI /DOutputDir=build\release installers\windows\faceguard.iss
;
; * Se instala por usuario (sin pedir permisos de administrador) en
;   %LOCALAPPDATA%\Programs\FaceGuard AI.
; * Los datos (personas, historial, configuración) viven en %LOCALAPPDATA%\FaceGuard AI
;   y NO se borran al actualizar. Al desinstalar se pregunta si se quieren borrar.
; * Instalar una versión nueva encima de la anterior es la forma de actualizar.

#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif
#ifndef SourceDir
  #define SourceDir "..\..\build\dist\FaceGuardAI"
#endif
#ifndef OutputDir
  #define OutputDir "..\..\build\release"
#endif

[Setup]
; AppId fijo: permite que cada versión nueva reemplace a la anterior.
AppId={{6E3C2B7A-9F1D-4C55-8E2A-3B7D41F0A9C2}
AppName=FaceGuard AI
AppVersion={#AppVersion}
AppVerName=FaceGuard AI {#AppVersion}
AppPublisher=FaceGuard AI
AppPublisherURL=https://github.com/Galito1014/FaceGuard
AppSupportURL=https://github.com/Galito1014/FaceGuard/issues
AppUpdatesURL=https://github.com/Galito1014/FaceGuard/releases
DefaultDirName={autopf}\FaceGuard AI
DefaultGroupName=FaceGuard AI
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#OutputDir}
OutputBaseFilename=FaceGuardAI-Desktop-{#AppVersion}-windows-x64-setup
SetupIconFile=..\assets\faceguard.ico
UninstallDisplayIcon={app}\FaceGuardAI.exe
LicenseFile=..\..\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Borra los archivos del programa anterior (no los datos del usuario) antes de copiar la versión nueva.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\FaceGuard AI"; Filename: "{app}\FaceGuardAI.exe"
Name: "{autodesktop}\FaceGuard AI"; Filename: "{app}\FaceGuardAI.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\FaceGuardAI.exe"; Description: "{cm:LaunchProgram,FaceGuard AI}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\FaceGuard AI');
    if DirExists(DataDir) then
      if MsgBox('¿Desea borrar también los datos de FaceGuard AI (personas registradas, fotografías, historial y configuración)?'
                + #13#10#13#10 + 'Si elige "No", se conservarán en:' + #13#10 + DataDir,
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
