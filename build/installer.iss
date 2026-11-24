; 电力王 —— 安装包脚本（Inno Setup 6）
; 编译：ISCC.exe build\installer.iss

#define AppName "电力王"
#define AppVersion "1.1.0"
#define AppExe "电力王.exe"
#define AppId "{{2C7B1D94-6E3A-4F58-9B7D-1A5C8E2F4D63}"
#define RootDir "D:\DeepSeek Harness\PeripheralBattery"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=himlaya
AppComments=无线鼠标 / 键盘 / 手柄电量监视器（本地运行，不联网）
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir={#RootDir}\dist
OutputBaseFilename={#AppName}-{#AppVersion}-安装程序
SetupIconFile={#RootDir}\assets\app.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=no
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
AllowNoIcons=yes
UsePreviousAppDir=yes
MinVersion=10.0

[Languages]
Name: "chinesesimplified"; MessagesFile: "{#RootDir}\build\lang\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式(&D)"; GroupDescription: "附加任务："; Flags: checkedonce
Name: "autostart"; Description: "开机时自动启动(&S)"; GroupDescription: "附加任务："; Flags: unchecked

[Files]
Source: "{#RootDir}\dist\电力王\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "无线外设电量监视器"
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "电力王"; ValueData: """{app}\{#AppExe}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#AppExe}"; Description: "立即运行 {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  { 安装前关掉正在运行的旧版本，否则文件会被占用 }
  Exec('taskkill.exe', '/IM 电力王.exe /F', '', SW_HIDE,
       ewWaitUntilTerminated, ResultCode);
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
    Exec('taskkill.exe', '/IM 电力王.exe /F', '', SW_HIDE,
         ewWaitUntilTerminated, ResultCode);
end;
