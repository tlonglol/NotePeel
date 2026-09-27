from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    

    # AWS S3 settings (also works with any S3-compatible endpoint)
    s3_bucket_name: str = ""
    s3_region: str = "us-east-1"
    s3_access_key_id: str = ""        # optional: omit to use an IAM role on AWS
    s3_secret_access_key: str = ""    # optional: omit to use an IAM role on AWS
    s3_endpoint: str = ""             # optional: only for S3-compatible providers



    # App settings
    app_name: str = "NotePeel"
    debug: bool = True
    
    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/notepeel"
    
    # JWT Auth
    secret_key: str = "your-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    
    # File upload settings
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    allowed_extensions: set = {"png", "jpg", "jpeg", "gif", "bmp", "tiff"}
    
    # Google Cloud - supports both API key and service account (optional now)
    google_cloud_api_key: str = ""
    google_application_credentials: str = ""
    
    # Google OAuth
    google_client_id: str = ""

    # Gemini AI
    gemini_api_key: str = ""

    # Cloudflare Workers AI
    cf_account_id: str = ""
    cf_api_token: str = ""

    # Retrieval ("ask your notes"). Embeddings come from Gemini (same key as OCR).
    # 768 dims via Matryoshka truncation of gemini-embedding-001; see DECISIONS.md.
    rag_embedding_model: str = "gemini-embedding-001"
    rag_embedding_dims: int = 768
    rag_embed_on_ingest: bool = True     # set false to index lexically only (no API calls)
    # Retrieval mode the ask endpoint uses: "vector" (default, measured best on the
    # eval corpus) or "hybrid" (RRF of FTS + vector). Hybrid's lexical weight of 0.5
    # is the value at which it ties vector-only; 1.0 measurably hurt. See DECISIONS.md.
    rag_retrieval_mode: str = "vector"
    rag_hybrid_fts_weight: float = 0.5
    rag_rrf_k: int = 60
    rag_candidates: int = 20

    # Grounded generation. Both Gemini models are capped at 20 generate_content
    # requests PER DAY PER MODEL on the free tier (measured 2026-09-26, DECISIONS.md
    # D32) -- flash is not a fix for flash-lite's cap, it has the identical cap under
    # a different counter. Since billing is off (owner's choice, D37), the app runs a
    # fallback chain instead: try Gemini first (better citations, JSON-enforced), and
    # on a quota/429 error fall back to the unthrottled Workers AI Llama model.
    rag_generation_model: str = "gemini-2.5-flash"
    rag_fallback_model: str = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    rag_context_chunks: int = 5           # chunks handed to the generator
    rag_abstain_threshold: float = 0.65   # top-1 cosine below this = weak evidence (DECISIONS D26)
    rag_max_answer_tokens: int = 600
    rag_streaming_enabled: bool = False   # SSE endpoint; real streaming on Lambda needs the Web Adapter

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
