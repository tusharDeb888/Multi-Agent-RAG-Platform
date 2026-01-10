"""
Hallucination detection utilities for RAG system.
"""
import re
from typing import Optional


def detect_hallucination(answer: str, context: str, query: str) -> Optional[str]:
    """
    Post-generation hallucination detector.
    Returns error message if hallucination detected, None otherwise.
    
    Detection Rules:
    1. Code Generation: Block if answer contains code blocks but context doesn't
    2. Generic Patterns: Block common hallucination phrases
    3. Length Mismatch: Block if answer is much longer than context (fabrication)
    """
    
    # Rule 1: Code Generation Detection
    answer_has_code = bool(re.search(r'```\w+', answer)) or bool(re.search(r'import \w+|def \w+\(|class \w+:', answer))
    context_has_code = bool(re.search(r'```\w+', context)) or bool(re.search(r'import \w+|def \w+\(|class \w+:', context))
    
    if answer_has_code and not context_has_code:
        return "Code generation detected without code in context"
    
    # Rule 2: Generic Hallucination Patterns
    hallucination_patterns = [
        r"Here is the code to get started:",
        r"Here's how you can",
        r"You can use the following",
        r"import pandas as pd",  # Common fabricated example
        r"df = pd\.read_",       # Data frame hallucination
        r"Let me explain",
        r"In general,",
        r"Typically,",
        r"Usually,",
    ]
    
    for pattern in hallucination_patterns:
        if re.search(pattern, answer, re.IGNORECASE):
            return f"Generic explanation pattern: {pattern}"
    
    # Rule 3: Fabrication Detection (Answer much longer than context)
    # If answer is >2x longer than context and doesn't cite much, likely fabricated
    answer_words = len(answer.split())
    context_words = len(context.split())
    citation_count = len(re.findall(r'\[\[(\d+)\]\]', answer))
    
    if context_words > 0 and answer_words > context_words * 2 and citation_count < 2:
        return f"Fabrication: Answer ({answer_words}w) >> Context ({context_words}w) with sparse citations"
    
    return None
