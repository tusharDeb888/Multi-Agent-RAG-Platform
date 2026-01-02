from enum import Enum

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
