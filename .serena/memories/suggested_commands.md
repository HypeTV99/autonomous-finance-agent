# Suggested Project Commands (Windows PowerShell)

## Local Testing & Verification
```powershell
# Run full unit & integration test suite (must pass 62/62)
.\venv\Scripts\pytest.exe -q

# Run live system integration verification against Cloud Run (28/28)
python scratch/test_system.py
```

## Cloud Build & Deployment
```powershell
# Build container image on GCP Cloud Build (optimizes tarball using .dockerignore/.gcloudignore)
gcloud builds submit --tag gcr.io/financex-506313/finance-agent:<tag> --project financex-506313

# Deploy to Cloud Run
gcloud run deploy finance-agent --image gcr.io/financex-506313/finance-agent:<tag> --region asia-south1 --platform managed --allow-unauthenticated --project financex-506313
```

## Serena Management
```powershell
# Check project health & LSP status
serena project health-check

# Re-index symbols in workspace
serena project index

# Verify memory references
serena memories check
```
