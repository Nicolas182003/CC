@echo off
REM Double-click launcher for the technician. No console, no venv activation, no
REM commands to remember: it calls the environment's Python directly.
REM
REM Output is deliberately plain ASCII. The console codepage mangles accents, and
REM a technician reading garbled text assumes something broke.

title Clariot - Procesar alertas
cd /d "%~dp0"

echo ==================================================
echo   CLARIOT - Procesando alertas
echo ==================================================
echo.
echo Outlook tiene que estar abierto.
echo Si no lo esta: cerra esta ventana, abri Outlook,
echo y volve a hacer doble clic aqui.
echo.
echo --------------------------------------------------

".venv\Scripts\python.exe" -m clariot
set CODIGO=%ERRORLEVEL%

echo --------------------------------------------------
echo.
if "%CODIGO%"=="0" (
    echo   LISTO. Revisa en Outlook, en este orden:
    echo.
    echo     1. Borradores / Urgencias    ^<- enviar HOY
    echo     2. Borradores / Por enviar   ^<- rutina
    echo.
    echo   En cada borrador: pone el destinatario,
    echo   reemplaza [NOMBRE], completa la RECOMENDACION
    echo   DE EMELTEC, lee y envia.
) else (
    echo   TERMINO CON PROBLEMAS.
    echo   Mira el detalle arriba, o abri logs\clariot.log
)
echo.
echo ==================================================
echo.
pause
