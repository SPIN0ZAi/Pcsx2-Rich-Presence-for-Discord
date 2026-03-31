# build_release.ps1
# Script to build a clean distribution of PCSX2 Rich Presence for Windows

Write-Host "Cleaning old builds..."
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

Write-Host "Running PyInstaller..."
# We use --onedir (default) instead of --onefile because Python 3.13 + PyInstaller OneFile 
# sometimes struggles with unpacking python313.dll into the temporary directory.
# This creates a folder at dist\pcsx2-rpc\ with the .exe and all its DLLs inside.
pyinstaller --noconfirm --name pcsx2-rpc --windowed --icon assets/ps2_icon.png --hidden-import pystray --hidden-import PIL --hidden-import pystray._win32 --add-data "config.yaml;." --add-data "assets/ps2_icon.png;assets" launcher.py

Write-Host "Zipping the release..."
Compress-Archive -Path "dist\pcsx2-rpc" -DestinationPath "dist\pcsx2-rpc-windows-x64.zip" -Force

Write-Host "Done! The release zip is located at: dist\pcsx2-rpc-windows-x64.zip"
Write-Host "Extract that folder anywhere and run pcsx2-rpc.exe"
