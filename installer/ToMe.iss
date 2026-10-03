; ============================================================
;  念 ToMe — Windows 安装包脚本 (Inno Setup 6.3+)
;
;  构建：  ISCC.exe ToMe.iss
;  产物：  ..\dist\ToMe-Setup-1.0.0.exe
;
;  安装内容：ToMe.exe 单文件主程序
;  额外能力：桌面快捷方式、开始菜单项、「应用和功能」卸载项、
;            可选的开机自动启动（写 HKCU\...\Run\ToMe）
; ============================================================

#define MyAppName        "念 ToMe"
#define MyAppNameEn      "ToMe"
#define MyAppVersion     "1.0.0"
#define MyAppVerFull     "1.0.0.0"
#define MyAppExeName     "ToMe.exe"
#define MyAppPublisher   "ToMe"
#define MyAppURL         "https://example.invalid/ToMe"
#define MyAppId          "{{B7E4C1A9-3F52-4D8E-9A17-6C0D5E2F81B3}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
VersionInfoVersion={#MyAppVerFull}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} 安装程序
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVerFull}

; 默认按用户安装（不需要管理员）；允许用户在向导里改成「为所有用户安装」
DefaultDirName={autopf}\ToMe
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Win10 19041+ / x64，与主程序要求一致
MinVersion=10.0.19041
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

OutputDir=..\dist
OutputBaseFilename=ToMe-Setup-{#MyAppVersion}
SetupIconFile=..\assets\tome.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
DisableDirPage=auto
DisableReadyPage=no

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
chinesesimplified.AutoStartTask=开机自动启动 {#MyAppName}
english.AutoStartTask=Start {#MyAppNameEn} when Windows starts
chinesesimplified.LaunchApp=立即启动 {#MyAppName}
english.LaunchApp=Launch {#MyAppNameEn}

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
; checkedonce = 首次安装默认勾选，之后记住用户的选择
Name: "autostart"; Description: "{cm:AutoStartTask}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

; 开机自启：写当前用户的 Run 键（程序内「开机自动启动」开关操作的是同一个键，
; 所以安装时勾选 / 装完在设置里切换，两边状态始终一致；卸载时一并删除）
[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "ToMe"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM {#MyAppExeName} /F"; Flags: runhidden; RunOnceId: "KillToMe"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
{ 安装/覆盖安装前先结束正在运行的 ToMe：它是托盘挂件，没有主窗口，
  Restart Manager 不一定能正常关闭它，所以直接结束进程最稳妥。}
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM {#MyAppExeName} /F',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;
