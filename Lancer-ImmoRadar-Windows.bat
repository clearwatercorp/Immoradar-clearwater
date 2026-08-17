@echo off
REM Double-cliquez sur ce fichier pour lancer ImmoRadar.
REM (Aucune ligne de commande a taper : une fenetre s'ouvre, le navigateur aussi.)

cd /d "%~dp0"

echo ==========================================
echo   ImmoRadar Invest
echo ==========================================
echo.

REM 1. Python installe ? (py est le lanceur officiel Windows, python en repli)
set PYTHON_CMD=
where py >nul 2>nul && set PYTHON_CMD=py -3
if "%PYTHON_CMD%"=="" (
    where python >nul 2>nul && set PYTHON_CMD=python
)
if "%PYTHON_CMD%"=="" (
    echo [X] Python 3 n'est pas installe sur ce PC.
    echo.
    echo     Telechargez-le ici ^(bouton jaune "Download Python"^) :
    echo     https://www.python.org/downloads/
    echo.
    echo     IMPORTANT : cochez "Add Python to PATH" pendant l'installation.
    echo     Puis double-cliquez a nouveau sur ce fichier.
    echo.
    pause
    exit /b 1
)

REM 2. Environnement isole (cree une seule fois, reutilise ensuite)
if not exist ".venv" (
    echo [*] Premiere installation ^(une minute environ^)...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 (
        echo [X] Impossible de creer l'environnement Python.
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate.bat

REM 3. Dependances (rapide si deja installees)
echo [*] Verification des dependances...
python -m pip install --quiet --upgrade pip >nul 2>nul
python -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo [X] Installation des dependances impossible ^(connexion internet ?^).
    pause
    exit /b 1
)

REM 4. Ouverture du navigateur une fois le serveur pret
start "" /b cmd /c "timeout /t 4 >nul & start http://localhost:3000"

echo.
echo [OK] Demarrage... le navigateur va s'ouvrir sur http://localhost:3000
echo.
echo      Les annonces arrivent progressivement ^(1 a 2 min au premier lancement^).
echo      /!\ Gardez CETTE FENETRE OUVERTE tant que vous utilisez l'outil.
echo      Pour arreter : fermez cette fenetre, ou appuyez sur Ctrl+C.
echo.
echo ==========================================
echo.

python server.py

echo.
echo Serveur arrete.
pause
