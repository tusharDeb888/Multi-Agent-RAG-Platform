"""
Prompt Firewall for PII and Sensitive Data Redaction.
Sanitizes text before sending it to the LLM to prevent data leakage.
"""
import re
from typing import List, Pattern

class PromptFirewall:
    """
    Firewall to detect and redact patterns from text.
    """
    
    def __init__(self):
        self._patterns: List[dict] = [
            # Email
            {
                "name": "EMAIL",
                "regex": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
                "replacement": "[EMAIL REDACTED]"
            },
            # Credit Card (Simple 16 digit check, could be improved with Luhn)
            {
                "name": "CREDIT_CARD",
                "regex": re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b'),
                "replacement": "[CREDIT_CARD REDACTED]"
            },
            # Indian PAN Card (5 letters, 4 digits, 1 letter)
            {
                "name": "PAN_CARD",
                "regex": re.compile(r'\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b'),
                "replacement": "[PAN REDACTED]"
            },
            # Indian Aadhaar (12 digits, often space separated 4-4-4)
            # Be careful not to match generic 12 digit numbers lightly, but strictness is better here.
            {
                "name": "AADHAAR",
                "regex": re.compile(r'\b\d{4}\s\d{4}\s\d{4}\b'),
                "replacement": "[UID REDACTED]"
            },
            # Standard generic 10-digit phone/mobile (Indian context common)
            {
                "name": "PHONE",
                # Matches +91-9999999999 or 9876543210
                "regex": re.compile(r'(?:\+91[\-\s]?)?[789]\d{9}\b'),
                "replacement": "[PHONE REDACTED]"
            }
        ]

    def sanitize(self, text: str) -> str:
        """
        Redact known patterns from the text.
        """
        if not text:
            return ""
            
        sanitized_text = text
        for pattern in self._patterns:
            sanitized_text = pattern["regex"].sub(pattern["replacement"], sanitized_text)
            
        return sanitized_text

    def check_for_financials(self, text: str) -> bool:
        """
        Heuristic to check if text contains generic financial numbers ($/Rs symbols with numbers).
        Not auto-redacting yet as it might be relevant, but useful for warning.
        """
        # TODO: Implement strict financial redaction if required.
        pass
