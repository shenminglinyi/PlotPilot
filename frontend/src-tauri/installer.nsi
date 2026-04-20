; 【已弃用】曾作为 bundle.windows.nsis.template 使用。
; Tauri 2 官方模板为 Handlebars（见 crates/tauri-bundler/.../installer.nsi），
; 自定义整包替换会导致 ${SOURCE_DIR} 等变量未注入、打包失败。
; 如需定制请基于上游 installer.nsi 复制后改 template，或使用 installer_hooks 注入 .nsh。
;
; PlotPilot NSIS 安装脚本（保留作参考）
; 基于 Tauri 的 NSIS 模板，添加了桌面快捷方式和开始菜单配置

!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"

; 基础配置
Name "PlotPilot - AI 小说创作平台"
OutFile "${OUTFILE}"
Unicode True
RequestExecutionLevel admin

; 默认安装目录
InstallDir "$PROGRAMFILES64\PlotPilot"
InstallDirRegKey HKCU "Software\PlotPilot" "InstallDir"

; 版本信息
VIProductVersion "1.0.2.0"
VIAddVersionKey "ProductName" "PlotPilot"
VIAddVersionKey "FileDescription" "AI 小说创作平台"
VIAddVersionKey "FileVersion" "1.0.2"
VIAddVersionKey "ProductVersion" "1.0.2"
VIAddVersionKey "InternalName" "PlotPilot"
VIAddVersionKey "LegalCopyright" "© 2025 PlotPilot Team"
VIAddVersionKey "OriginalFilename" "PlotPilot_1.0.2_x64-setup.exe"

; MUI 界面配置（脚本位于 target/release/nsis/x64/，需回到 src-tauri/icons）
!define MUI_ICON "..\..\..\..\icons\icon.ico"
!define MUI_UNICON "..\..\..\..\icons\icon.ico"
; 不使用 Contrib\Graphics 下 bmp（binary-releases 的精简 NSIS 可能不含这些文件）
!define MUI_ABORTWARNING

; 凡使用 $变量的页面宏之前必须先声明（否则 StrCpy 报错）
Var StartMenuFolder

; 欢迎页面
!insertmacro MUI_PAGE_WELCOME

; 许可协议页面（可选）
; !insertmacro MUI_PAGE_LICENSE "license.txt"

; 安装目录选择页面
!insertmacro MUI_PAGE_DIRECTORY

; 开始菜单快捷方式页面
!define MUI_STARTMENUPAGE_REGISTRY_ROOT "HKCU"
!define MUI_STARTMENUPAGE_REGISTRY_KEY "Software\PlotPilot"
!define MUI_STARTMENUPAGE_REGISTRY_VALUENAME "StartMenuFolder"
!insertmacro MUI_PAGE_STARTMENU Application $StartMenuFolder

; 安装页面
!insertmacro MUI_PAGE_INSTFILES

; 完成页面 - 添加"运行程序"和"创建桌面快捷方式"选项
!define MUI_FINISHPAGE_RUN "$INSTDIR\PlotPilot.exe"
!define MUI_FINISHPAGE_RUN_TEXT "立即运行 PlotPilot"
!define MUI_FINISHPAGE_SHOWREADME ""
!define MUI_FINISHPAGE_SHOWREADME_TEXT "创建桌面快捷方式"
!define MUI_FINISHPAGE_SHOWREADME_FUNCTION CreateDesktopShortcut
!insertmacro MUI_PAGE_FINISH

; 卸载页面
!insertmacro MUI_UNPAGE_WELCOME
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

; 语言选择（须在页面宏之后，见 NSIS Modern UI 文档）
!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

; 安装部分
Section "Install"
  SetOutPath "$INSTDIR"

  ; 复制所有文件
  File /r "${SOURCE_DIR}\*"

  ; 写入卸载程序
  WriteUninstaller "$INSTDIR\uninstall.exe"

  ; 写入注册表信息
  WriteRegStr HKCU "Software\PlotPilot" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\PlotPilot" "Version" "1.0.2"

  ; 写入卸载注册表项（控制面板中显示）
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\PlotPilot" \
    "DisplayName" "PlotPilot - AI 小说创作平台"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\PlotPilot" \
    "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\PlotPilot" \
    "DisplayIcon" "$INSTDIR\PlotPilot.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\PlotPilot" \
    "Publisher" "PlotPilot Team"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\PlotPilot" \
    "DisplayVersion" "1.0.2"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\PlotPilot" \
    "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\PlotPilot" \
    "NoRepair" 1

  ; 计算安装目录大小
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\PlotPilot" \
    "EstimatedSize" "$0"

  ; 创建开始菜单快捷方式
  !insertmacro MUI_STARTMENU_WRITE_BEGIN Application
    CreateDirectory "$SMPROGRAMS\$StartMenuFolder"
    CreateShortcut "$SMPROGRAMS\$StartMenuFolder\PlotPilot.lnk" "$INSTDIR\PlotPilot.exe"
    CreateShortcut "$SMPROGRAMS\$StartMenuFolder\卸载 PlotPilot.lnk" "$INSTDIR\uninstall.exe"
  !insertmacro MUI_STARTMENU_WRITE_END

SectionEnd

; 创建桌面快捷方式的函数
Function CreateDesktopShortcut
  CreateShortcut "$DESKTOP\PlotPilot.lnk" "$INSTDIR\PlotPilot.exe" "" "$INSTDIR\PlotPilot.exe" 0
FunctionEnd

; 卸载部分
Section "Uninstall"
  ; 删除安装目录中的所有文件
  RMDir /r "$INSTDIR"

  ; 删除开始菜单快捷方式
  !insertmacro MUI_STARTMENU_GETFOLDER Application $StartMenuFolder
  RMDir /r "$SMPROGRAMS\$StartMenuFolder"

  ; 删除桌面快捷方式
  Delete "$DESKTOP\PlotPilot.lnk"

  ; 删除注册表项
  DeleteRegKey HKCU "Software\PlotPilot"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\PlotPilot"

SectionEnd
