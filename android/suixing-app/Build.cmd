@echo off
setlocal
cd /d "%~dp0"
if exist "D:\Android\java\jdk-21.0.13.1+2\bin\java.exe" set "JAVA_HOME=D:\Android\java\jdk-21.0.13.1+2"
call "%~dp0gradlew.bat" %*
exit /b %ERRORLEVEL%
