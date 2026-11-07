@echo off
REM ==============================================================================
REM Thamarayyath Employee Portal -- Windows Firewall Configuration
REM Run as Administrator to allow inbound LAN connections on port 8000
REM ==============================================================================

echo Configuring Windows Defender Firewall for Thamarayyath Employee Portal...
echo.

netsh advfirewall firewall show rule name="Thamarayyath Employee Portal (Port 8000)" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo Firewall rule already exists. Updating rule...
    netsh advfirewall firewall delete rule name="Thamarayyath Employee Portal (Port 8000)"
)

netsh advfirewall firewall add rule name="Thamarayyath Employee Portal (Port 8000)" dir=in action=allow protocol=TCP localport=8000 profile=private,domain description="Allows authorized LAN PCs to access Thamarayyath Employee Portal"

if %ERRORLEVEL% equ 0 (
    echo.
    echo [SUCCESS] Port 8000 is now open on Private/Domain LAN networks!
    echo Other computers connected to your company Wi-Fi/switch can now access the portal.
) else (
    echo.
    echo [ERROR] Failed to add firewall rule. Make sure you Right-Click -> Run as Administrator.
)

echo.
pause
