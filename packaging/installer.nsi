; Ember — Copyright (C) 2026 Ember contributors.
; SPDX-License-Identifier: GPL-3.0-or-later
Unicode True
!include "MUI2.nsh"
!include "x64.nsh"
!include "WinVer.nsh"
!ifndef PAYLOAD
!error "Pass /DPAYLOAD=absolute-path-to-dist/Ember"
!endif
!ifndef OUTPUT
!define OUTPUT "Ember-Setup.exe"
!endif
Name "Ember"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\Ember"
InstallDirRegKey HKCU "Software\Ember" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
!ifndef EMBER_VERSION
!error "Pass /DEMBER_VERSION=version from ember/__init__.py"
!endif
!ifndef EMBER_VERSION_QUAD
!error "Pass /DEMBER_VERSION_QUAD=major.minor.patch.0"
!endif
VIProductVersion "${EMBER_VERSION_QUAD}"
VIAddVersionKey /LANG=1033 "ProductName" "Ember"
VIAddVersionKey /LANG=1033 "FileDescription" "Ember Setup (preview)"
VIAddVersionKey /LANG=1033 "FileVersion" "${EMBER_VERSION}"
VIAddVersionKey /LANG=1033 "LegalCopyright" "2026 Ember contributors; upstream Midrag and contributors"
!define MUI_ICON "..\ember\web\Ember.ico"
!define MUI_UNICON "..\ember\web\Ember.ico"
!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\Ember.exe"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "Russian"

Function .onInit
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_ICONSTOP "Ember requires Windows 10 or Windows 11."
    Abort
  ${EndIf}
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "Ember requires 64-bit Windows."
    Abort
  ${EndIf}
  !insertmacro MUI_LANGDLL_DISPLAY
FunctionEnd

Function CheckAppClosed
  IfFileExists "$INSTDIR\Ember.exe" 0 app_closed
  ExecWait '$\"$INSTDIR\Ember.exe$\" --can-update' $0
  ${If} $0 != 0
    MessageBox MB_ICONSTOP "Close Ember before installing or updating it."
    Abort
  ${EndIf}
app_closed:
FunctionEnd

Section "Ember" SEC_APP
  Call CheckAppClosed
  SetShellVarContext current
  SetOutPath "$INSTDIR"
  File /r "${PAYLOAD}\*.*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\Ember"
  CreateShortcut "$SMPROGRAMS\Ember\Ember.lnk" "$INSTDIR\Ember.exe" "" "$INSTDIR\_internal\ember\web\Ember.ico"
  CreateShortcut "$SMPROGRAMS\Ember\Stop Ember.lnk" "$INSTDIR\Ember.exe" "--stop"
  CreateShortcut "$SMPROGRAMS\Ember\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\Ember.lnk" "$INSTDIR\Ember.exe" "" "$INSTDIR\_internal\ember\web\Ember.ico"
  WriteRegStr HKCU "Software\Ember" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Ember" "DisplayName" "Ember"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Ember" "DisplayVersion" "${EMBER_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Ember" "Publisher" "Ch3L1k"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Ember" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Ember" "DisplayIcon" "$INSTDIR\Ember.exe"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Ember" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Ember" "NoRepair" 1
  IfSilent integration_done
  ExecWait '$\"$INSTDIR\Ember.exe$\" --enable-integration' $0
  ${If} $0 != 0
    MessageBox MB_ICONEXCLAMATION "Ember is installed, but automatic Steam integration could not be enabled. Launch Ember to retry."
  ${EndIf}
integration_done:
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  IfFileExists "$INSTDIR\Ember.exe" 0 unsafe_uninstall
  IfFileExists "$INSTDIR\_internal\EMBER-NOTICES.txt" 0 unsafe_uninstall
  ExecWait '$\"$INSTDIR\Ember.exe$\" --can-update' $0
  ${If} $0 != 0
    Goto running_uninstall
  ${EndIf}
  ExecWait '$\"$INSTDIR\Ember.exe$\" --uninstall-integration' $0
  ${If} $0 != 0
    SetErrorLevel 1
    Goto done_uninstall
  ${EndIf}
  ClearErrors
  Delete "$INSTDIR\Ember.exe"
  IfErrors running_uninstall
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\Ember-Source.zip"
  Delete "$INSTDIR\README.txt"
  Delete "$INSTDIR\LICENSE"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  ReadRegStr $1 HKCU "Software\Ember" "InstallDir"
  ${If} $1 != $INSTDIR
    Goto done_uninstall
  ${EndIf}
  Delete "$DESKTOP\Ember.lnk"
  RMDir /r "$SMPROGRAMS\Ember"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Ember"
  DeleteRegKey HKCU "Software\Ember"
  Goto done_uninstall
running_uninstall:
  MessageBox MB_ICONSTOP "Close Ember before uninstalling. User data and Steam files have been kept."
  SetErrorLevel 1
  Goto done_uninstall
unsafe_uninstall:
  MessageBox MB_ICONSTOP "Ember installation markers are missing. No files were removed."
  SetErrorLevel 1
done_uninstall:
SectionEnd
