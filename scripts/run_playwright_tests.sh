#!/usr/bin/env bash
# ==============================================================================
# Run Playwright E2E & Responsive Tests for Autonomous AP & Treasury Cockpit
# ==============================================================================
set -euo pipefail

echo "[INFO] Installing dev dependencies and playwright browser if needed..."
python -m pip install -r requirements-dev.txt --quiet
python -m playwright install chromium

echo "[INFO] Running Playwright UI tests..."
pytest -q -m playwright --tracing=retain-on-failure --screenshot=only-on-failure --output=artifacts/playwright "$@"
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "[SUCCESS] All Playwright UI tests passed successfully."
else
    echo "[ERROR] Playwright tests failed with exit code $EXIT_CODE."
fi

exit $EXIT_CODE
