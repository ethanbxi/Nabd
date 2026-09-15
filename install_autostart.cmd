@echo off
REM ============================================================
REM   Nab'd - start at sign-in, ahead of everything else
REM   RIGHT-CLICK THIS FILE  ->  "Run as administrator"
REM ============================================================
REM
REM Task Scheduler fires logon triggers before Explorer works through the Run
REM key, so this lets Nab'd call RegisterHotKey before the overlays and clip
REM recorders that would otherwise claim Insert first. Creating a logon task
REM needs admin once; the task itself runs unelevated, so Nab'd still starts
REM as a normal user program.
REM
REM The Run-key entry stays as a backstop - Nab'd's single-instance mutex
REM means whichever launch comes second just exits.

echo Creating the Nab'd logon task...
schtasks /Create /TN "Nabd" /XML "%~dp0autostart_task.xml" /F
if errorlevel 1 goto failed

echo.
echo Creating the one-shot Insert diagnostic...
schtasks /Create /TN "NabdInsertHunt" /XML "%~dp0insert_hunt_task.xml" /F
if errorlevel 1 echo   (diagnostic task failed - not fatal)

echo.
echo Done. Reboot, then Nab'd starts before the Run-key apps.
echo The diagnostic writes insert_hunt.log and removes itself.
echo.
pause
exit /b 0

:failed
echo.
echo FAILED - was this run as administrator?
echo.
pause
exit /b 1
