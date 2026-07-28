@echo off
REM Entry point for the Windows Scheduled Task.
REM The task MUST use an "At log on" trigger with repetition: Outlook COM needs
REM an interactive desktop session and fails under "run whether logged on or not".

cd /d "%~dp0"
".venv\Scripts\python.exe" -m clariot %*
