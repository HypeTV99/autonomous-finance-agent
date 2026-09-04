@echo off
REM ==============================================================================
REM Run Playwright E2E & Responsive Tests for Autonomous AP & Treasury Cockpit
REM ==============================================================================

echo [INFO] Installing dev dependencies and playwright browser if needed...
python -m pip install -r requirements-dev.txt --quiet
python -m playwright install chromium

echo [INFO] Running Playwright UI tests...
pytest -q -m playwright --tracing=retain-on-failure --screenshot=only-on-failure --output=artifacts/playwright %*
set EXIT_CODE=%ERRORLEVEL%

if %EXIT_CODE% equ 0 (
    echo [SUCCESS] All Playwright UI tests passed successfully.
) else (
    echo [ERROR] Playwright tests failed with exit code %EXIT_CODE%.
)

exit /b %EXIT_CODE%
