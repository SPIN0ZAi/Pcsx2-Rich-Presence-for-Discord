# build_release.ps1
# Script to build a clean distribution of EmuPresence for Windows

Write-Host "Cleaning old builds..."
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

Write-Host "Running PyInstaller..."
# We use --onedir (default) instead of --onefile because Python 3.13 + PyInstaller OneFile 
# sometimes struggles with unpacking python313.dll into the temporary directory.
# This creates a folder at dist\EmuPresence\ with the .exe and all its DLLs inside.
pyinstaller --noconfirm --name EmuPresence --windowed --icon assets/ps2_icon.png --hidden-import pystray --hidden-import PIL --hidden-import pystray._win32 --add-data "assets/ps2_icon.png;assets" launcher.py

Write-Host "Zipping the release..."
Compress-Archive -Path "dist\EmuPresence" -DestinationPath "dist\EmuPresence-windows-x64.zip" -Force

Write-Host "Done! The release zip is located at: dist\EmuPresence-windows-x64.zip"
Write-Host "Extract that folder anywhere and run EmuPresence.exe"
