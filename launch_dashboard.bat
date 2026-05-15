@echo off
echo.
echo =================================================
echo   SMC-AI MORNING BRIEF v2 -- Dashboard Launcher
echo =================================================
echo.
echo Lancement SMC-AI Dashboard...

REM Activer le venv (.venv en priorite, puis venv, puis env)
if exist .venv\Scripts\activate (
    call .venv\Scripts\activate
) else if exist venv\Scripts\activate (
    call venv\Scripts\activate
) else if exist env\Scripts\activate (
    call env\Scripts\activate
) else (
    echo  [WARN] Aucun venv trouve -- utilisation du Python systeme
)
python launch_dashboard.py

pause
