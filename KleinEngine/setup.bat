@echo off
rem Builds this folder's own Python. Everything stays inside KleinEngine, and no admin rights are needed.
cd /d "%~dp0"
set CONDA_PKGS_DIRS=%~dp0.conda_pkgs
set PIP_CACHE_DIR=%~dp0.conda_pkgs\pip
if not exist env (
    call "%USERPROFILE%\miniconda3\Scripts\conda.exe" create -y -p "%~dp0env" --override-channels -c conda-forge python=3.11 pip || exit /b 1
)
env\python.exe -m pip install --no-input torch==2.7.0 --index-url https://download.pytorch.org/whl/cu126 || exit /b 1
env\python.exe -m pip install --no-input diffusers==0.38.0 transformers==5.7.0 accelerate safetensors pillow numpy python-dateutil || exit /b 1
env\python.exe download_word_list.py || exit /b 1
echo SETUP DONE
