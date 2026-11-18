@echo off
setlocal
rem Instala a skill /replai no Claude. Quem instala pelo proprio Claude nao precisa deste arquivo:
rem o Claude roda scripts\instalar.py. Este .bat so garante o Python e chama o mesmo instalador.
rem Uso / usage: dois cliques / double-click, ou / or "instalar.bat /s" (silencioso / silent).
set "SILENCIO="
if /i "%~1"=="/s" set "SILENCIO=1"
title Replai - instalacao / install
echo.
echo  Instalando o Replai / Installing Replai...
echo.

set "PY="
set "PYLOCAL=%LocalAppData%\Programs\Python\Python312\python.exe"
where python >nul 2>nul && python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY (
  where py >nul 2>nul && py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
)
if not defined PY if exist "%PYLOCAL%" set "PY="%PYLOCAL%""
if not defined PY (
  echo  Python nao encontrado, instalando pelo winget / Python not found, installing with winget...
  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
  if exist "%PYLOCAL%" set "PY="%PYLOCAL%""
)
if not defined PY (
  echo  ERRO: Python indisponivel. Reinicie o PC e rode de novo. / Python unavailable: restart and run again.
  goto :fim_erro
)

%PY% "%~dp0scripts\instalar.py"
if errorlevel 1 goto :fim_erro
echo.
echo  INSTALACAO OK / INSTALL OK
echo  Abra o Claude (aba Code) e digite / Open Claude (Code tab) and type:  /replai
echo.
if not defined SILENCIO pause
exit /b 0

:fim_erro
if not defined SILENCIO pause
exit /b 1
