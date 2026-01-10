"""
Configuration management using Pydantic Settings.
Follows Single Responsibility Principle - only handles configuration.
"""
from enum import Enum
from typing import Optional, List, Any
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator, AnyHttpUrl


class Environment(str, Enum):
    """Environment types."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    LLAMA_3_2 = "llama_3.2" 
    LOCAL = "local" # Generic local GGUF/Transformers
    LLAMA2 = "llama2"
    QWEN = "qwen"
    CUSTOM = "custom"
    OLLAMA = "ollama"


class VectorIndexType(str, Enum):
    """Vector index types."""
    ORACLE_VECTOR = "oracle_vector"
    MILVUS = "milvus"


class Settings(BaseSettings):
    """Application settings with validation."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Environment
    environment: Environment = Field(default=Environment.DEVELOPMENT)
    
    # Database
    oracle_host: str = Field(default="localhost")
    oracle_port: int = Field(default=1521)
    oracle_service_name: str = Field(default="XE")
    oracle_user: str = Field(default="system")
    oracle_password: str = Field(default="oracle")
    oracle_pool_size: int = Field(default=10, ge=1, le=100)
    oracle_max_overflow: int = Field(default=20, ge=0, le=200)
    # Default to None to use Oracle connection string
    custom_database_url: Optional[str] = Field(default=None)
    
    # LLM Configuration
    llm_provider: LLMProvider = Field(default=LLMProvider.LOCAL)
    llm_model_path: str = Field(default="./models/llama-3.2-3b-instruct-quantized.gguf")
    llm_quantization: str = Field(default="4bit")
    llm_context_length: int = Field(default=4096, ge=512, le=131072)
    llm_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=512, ge=1, le=4096)

    # Lazy Loading Configuration
    lazy_load_llm: bool = Field(default=False, description="Load LLM only on demand to save VRAM")
    llm_idle_timeout: int = Field(default=60, ge=0, description="Seconds before unloading idle LLM (0 for immediate, -1 for never)")
    
    # Vector Search
    vector_dimension: int = Field(default=384, ge=128, le=4096)
    vector_index_type: VectorIndexType = Field(default=VectorIndexType.MILVUS)
    index_storage_path: str = Field(default="./data/vector_index")
    bm25_index_path: str = Field(default="./data/vector_index.bm25_index")
    splade_index_path: str = Field(default="./data/vector_index.splade_index")
    splade_model_name: str = Field(default="naver/splade-cocondenser-ensembledistil")
    enable_splade: bool = Field(default=True)
    milvus_conn_uri: str = Field(default="http://localhost:19530")
    milvus_token: str = Field(default="") # For RBAC enabled Milvus
    
    # Embeddings
    embedding_device: str = Field(default="cpu", description="Device for embedding model (cpu, cuda, mps)")
    
    # Vision Configuration
    vision_provider: str = Field(default="ollama", pattern="^(ollama|local|vllm)$") 
    ollama_base_url: str = Field(default="http://localhost:11434")
    vllm_base_url: str = Field(default="http://vllm:8000/v1")
    vision_model_name: str = Field(default="moondream") # Efficient vision model
    vision_model_path: str = Field(default="./models/llava-v1.5-7b-Q4_K.gguf") # For local provider fallback

    
    # Security
    secret_key: str
    algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=480, ge=1)
    
    # Data Encryption (AES-256)
    encryption_key: str = Field(..., description="32-byte generic secure key (base64 encoded) for AES-256")
    enable_encryption: bool = Field(default=True)
    
    # Application
    app_name: str = Field(default="ISK-AI")
    app_version: str = Field(default="1.0.0")
    log_level: str = Field(default="INFO")
    api_prefix: str = Field(default="/api/v1")
    backend_cors_origins: List[AnyHttpUrl] = Field(default=["http://localhost:5173"])
    
    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> Any:
        if isinstance(v, str):
            if v.startswith("["):
                import json
                return json.loads(v)
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)
    
    # Document Processing
    max_document_size_mb: int = Field(default=500, ge=1, le=5000)
    chunk_size: int = Field(default=1000, ge=100, le=5000)
    chunk_overlap: int = Field(default=200, ge=0, le=1000)
    enable_ocr: bool = Field(default=True)
    
    # Caching
    cache_dir: str = Field(default="./data/cache")
    redis_url: str = Field(default="redis://localhost:6379/0")
    rate_limit_default: str = Field(default="100/minute", description="Default rate limit (e.g., '100/minute')")
    
    # Performance
    ingestion_workers: int = Field(default=4, ge=1, le=32)
    retrieval_top_k: int = Field(default=5, ge=1, le=50)
    rag_context_chunks: int = Field(default=3, ge=1, le=10)
    rerank_top_k: int = Field(default=20, ge=1, le=100)
    expansion_threshold: int = Field(default=20, ge=0, le=50)
    enable_query_expansion: bool = Field(default=True, description="Enable HyDE/Query Expansion")
    
    # Audit
    audit_log_path: str = Field(default="./data/audit.log")
    audit_retention_days: int = Field(default=365, ge=1, le=3650)
    enable_audit_logging: bool = Field(default=True)
    
    @field_validator("llm_quantization")
    @classmethod
    def validate_quantization(cls, v: str) -> str:
        """Validate quantization setting."""
        allowed = ["4bit", "8bit", "none"]
        if v.lower() not in allowed:
            raise ValueError(f"quantization must be one of {allowed}")
        return v.lower()
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        allowed = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return v.upper()
    
    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == Environment.DEVELOPMENT
    
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == Environment.PRODUCTION
    
    @property
    def database_url(self) -> str:
        """Construct database connection URL."""
        if self.custom_database_url:
            return self.custom_database_url
            
        return (
            f"oracle+oracledb://{self.oracle_user}:{self.oracle_password}"
            f"@{self.oracle_host}:{self.oracle_port}/{self.oracle_service_name}"
        )


# Global settings instance (Singleton pattern)
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get settings instance (Singleton)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings




