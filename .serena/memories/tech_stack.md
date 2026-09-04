# Technology Stack & Environment

## Runtime & Frameworks
- **Python**: 3.10 / 3.11 (Virtual environment at `.\venv\Scripts\python.exe`)
- **FastAPI / Uvicorn**: Web and REST API framework with `GZipMiddleware(minimum_size=1000)`
- **Pydantic v2**: Type schemas and serialization (`schemas.py`)
- **Cryptography**: `cryptography.hazmat.primitives.asymmetric.ed25519` with parsed key in-memory caching
- **Database / Store**: Google Cloud Firestore (`google-cloud-firestore`) with 60s in-memory TTL caching (`firestore_store.py`)
- **Testing**: `pytest` (62 automated unit/integration test suite)

## Cloud & Production Infrastructure
- **GCP Project**: `financex-506313`
- **Region**: `asia-south1` (Mumbai)
- **Deployment Platform**: Google Cloud Run (`finance-agent` service)
- **Container Registry**: Google Container Registry (`gcr.io/financex-506313/finance-agent`)
- **Live URL**: `https://finance-agent-83632260440.asia-south1.run.app`
