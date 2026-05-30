' TurboDown - Silent Launcher (No Console Window)
' Double-click this file to start TurboDown silently.
' The app will appear in the system tray near the clock.

Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

' Get the directory where this script is located (portable - works on any PC)
ScriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)
AppPath = ScriptDir & "\app.py"

' Check if app.py exists
If Not FSO.FileExists(AppPath) Then
    MsgBox "Error: app.py not found in:" & vbCrLf & ScriptDir & vbCrLf & vbCrLf & "Make sure this file is in the TurboDown folder.", vbCritical, "TurboDown"
    WScript.Quit
End If

' Launch TurboDown silently (0 = hidden window, False = don't wait)
WshShell.Run "pythonw """ & AppPath & """", 0, False
