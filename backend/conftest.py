import sys
import os
import pytest

# Add the current directory (backend/) to the Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Set dummy env vars so modules can import without real API keys
os.environ.setdefault("GEMINI_API_KEY", "test-dummy-key")
os.environ.setdefault("R2_ACCESS_KEY_ID", "test")
os.environ.setdefault("R2_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("R2_BUCKET_NAME", "test")
os.environ.setdefault("R2_ENDPOINT_URL", "https://test.r2.dev")
os.environ.setdefault("CF_ACCOUNT_ID", "test")
os.environ.setdefault("CF_API_TOKEN", "test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")

# Your existing fixture
@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"