@echo off
rem Compile AppleMusicLink.exe avec le compilateur C# fourni par Windows (.NET Framework 4.x), rien a installer.
cd /d "%~dp0"
"%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe" /nologo /codepage:65001 /target:winexe /optimize+ ^
  /out:AppleMusicLink.exe /win32icon:icone.ico ^
  /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.IO.Compression.dll /r:System.IO.Compression.FileSystem.dll ^
  AppleMusicLink.cs
