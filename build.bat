@echo off
chcp 65001 > nul
echo.
echo [yupoo_dl] Build
echo.

pip show pyinstaller > nul 2>&1
if errorlevel 1 (
    echo Instalando PyInstaller...
    pip install pyinstaller
)

echo Gerando executavel...
echo.

pyinstaller ^
    --onefile ^
    --console ^
    --name yupoo_dl ^
    --collect-all certifi ^
    --collect-all aiohttp ^
    --collect-all lxml ^
    --collect-all alive_progress ^
    --hidden-import aiohttp ^
    --hidden-import aiofiles ^
    --hidden-import bs4 ^
    --hidden-import lxml.etree ^
    --hidden-import lxml._elementpath ^
    yupoo_dl.py

echo.
echo Limpando arquivos temporarios...
rmdir /s /q build 2>nul
del yupoo_dl.spec 2>nul

echo.
if exist dist\yupoo_dl.exe (
    echo Executavel gerado com sucesso!
    echo Local: %~dp0dist\yupoo_dl.exe
) else (
    echo ERRO: build falhou.
)

echo.
pause
