from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class UserIntent(str, Enum):
    """
    Classifies the user's intent to drive response formatting.
    """
    FACT_LOOKUP = "fact_lookup"      # Who/What/When specific data
    DESCRIPTION = "description"      # "Tell me about...", explanation
    ENUMERATION = "enumeration"      # List, set of items
    COMPARISON = "comparison"        # X vs Y
    OPERATIONAL = "operational"      # How-to, procedure, steps
    NAVIGATION = "navigation"        # Find document X, Who is Person Y (Lookup)
    RESTRICTED = "restricted"        # Security sensitive keywords
    CHITCHAT = "chitchat"            # Small talk, greetings
    UNKNOWN = "unknown"              # Fallback

class RetrievalOutcome(str, Enum):
    """
    Classifies the state of the system after retrieval and policy checks.
    """
    STRONG_MATCH = "strong_match"       # High confidence chunks found
    PARTIAL_MATCH = "partial_match"     # Relevant but low score or incomplete
    NO_DATA = "no_data"                 # No chunks retrieved at all
    ACCESS_DENIED = "access_denied"     # Data exists but RBAC blocked it
    AMBIGUOUS = "ambiguous"             # Candidates found but rejected by reranker

class SourceChunk(BaseModel):
    """Represents a single retrieved chunk with metadata."""
    chunk_id: int
    document_id: int
    content: str
    similarity_score: float
    chunk_index: int
    document_title: Optional[str] = None
    page_number: Optional[int] = None
    
    class Config:
        from_attributes = True

class RetrievalResult(BaseModel):
    """Result of the retrieval process."""
    outcome: RetrievalOutcome
    chunks: List[SourceChunk] = []
    query_classified_intent: UserIntent = UserIntent.UNKNOWN
    debug_info: Optional[Dict[str, Any]] = None

class RAGResponse(BaseModel):
    """Standardized response to the user."""
    answer: str
    sources: List[SourceChunk] = []
    intent: UserIntent
    confidence_score: float = 0.0
    system_outcome: RetrievalOutcome
    metadata: Optional[Dict[str, Any]] = None

class QueryAnalysisResult(BaseModel):
    """Result of LLM query analysis."""
    intent: UserIntent = UserIntent.FACT_LOOKUP
    tone: str = "General"
    keywords: List[str] = []
    is_ambiguous: bool = False
