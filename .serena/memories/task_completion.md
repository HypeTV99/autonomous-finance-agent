# Task Completion Checklist

Before considering any task or refactoring complete:

1. **Local Pytest Suite**: Execute `.\venv\Scripts\pytest.exe -q` and confirm `62/62 PASSED (100%)`.
2. **Container Build**: Submit image with meaningful version tag (e.g. `gcr.io/financex-506313/finance-agent:v...`).
3. **Cloud Run Deployment**: Verify revision reaches 100% traffic allocation on `asia-south1`.
4. **Live Verification**: Run `python scratch/test_system.py` against `https://finance-agent-83632260440.asia-south1.run.app` and confirm `28/28 PASSED (100%)`.
5. **Serena Indexing**: Re-index project with `serena project index` to ensure LSP cache is up-to-date.
