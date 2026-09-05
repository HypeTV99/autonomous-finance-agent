import os
import pytest

# Ensure all automated test runs use fast, deterministic in-memory mock isolation
# and do not mutate shared production/live cloud infrastructure (Prompt 11 Rule 8).
os.environ["USE_MOCK_FIRESTORE"] = "true"
