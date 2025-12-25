; Sigil installer — ensure PATH updated (64-bit registry view + HKCU fallback)

!define APP_NAME "Sigil"
!define APP_EXE "sigil.exe"
!define APP_BAT "sig.bat"
!define INSTALL_DIR "C:\Sigil"
!define FILE_EXT ".sig"
!define WM_SETTINGCHANGE 0x001A

OutFile "Sigil_Setup.exe"
InstallDir "${INSTALL_DIR}"
RequestExecutionLevel admin

Name "${APP_NAME}"
Icon "sigil.ico"
UninstallIcon "sigil.ico"

ShowInstDetails show
ShowUninstDetails show

Page directory
Page instfiles
UninstPage instfiles

Section "Install Sigil"

    SetOutPath "$INSTDIR"

    ; Copy files
    File "sigil.exe"
    File "sig.bat"
    File "sigil.ico"

    ; ---------------------------
    ; Add to SYSTEM PATH (64-bit view)
    ; ---------------------------
    SetRegView 64
    ReadRegStr $0 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "Path"
    StrCpy $0 "$0;${INSTALL_DIR}"
    WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "Path" "$0"
    SetRegView 32

    ; ---------------------------
    ; Add to CURRENT USER PATH
    ; ---------------------------
    ReadRegStr $1 HKCU "Environment" "Path"
    StrCpy $1 "$1;${INSTALL_DIR}"
    WriteRegExpandStr HKCU "Environment" "Path" "$1"

    ; Notify system
    System::Call 'user32::SendMessageTimeoutA(i 0xffff, i ${WM_SETTINGCHANGE}, i 0, t "Environment", i 0, i 100, *i .r0)'

    ; ---------------------------
    ; File association (.sig)
    ; ---------------------------
    WriteRegStr HKCR "${FILE_EXT}" "" "SigilFile"
    WriteRegStr HKCR "SigilFile" "" "Sigil Script"
    WriteRegStr HKCR "SigilFile\DefaultIcon" "" "$INSTDIR\sigil.ico"
    WriteRegStr HKCR "SigilFile\shell\open\command" "" '"$INSTDIR\sigil.exe" "%1"'

    ; Uninstaller
    WriteUninstaller "$INSTDIR\Uninstall_Sigil.exe"

SectionEnd

Section "Uninstall"

    ; ---------------------------
    ; Remove plugins (IMPORTANT)
    ; ---------------------------
    RMDir /r "$INSTDIR\plugins"

    ; ---------------------------
    ; Remove core files
    ; ---------------------------
    Delete "$INSTDIR\sigil.exe"
    Delete "$INSTDIR\sig.bat"
    Delete "$INSTDIR\sigil.ico"
    Delete "$INSTDIR\Uninstall_Sigil.exe"

    ; Remove install directory
    RMDir "$INSTDIR"

    ; ---------------------------
    ; Registry cleanup (best-effort)
    ; ---------------------------
    SetRegView 64
    ReadRegStr $0 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "Path"
    SetRegView 32

    ReadRegStr $1 HKCU "Environment" "Path"

    System::Call 'user32::SendMessageTimeoutA(i 0xffff, i ${WM_SETTINGCHANGE}, i 0, t "Environment", i 0, i 100, *i .r0)'

    ; Remove file association
    DeleteRegKey HKCR "${FILE_EXT}"
    DeleteRegKey HKCR "SigilFile"

SectionEnd
