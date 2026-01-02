"""
Encryption Service handling AES-256-GCM.
"""
import base64
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.core.config import get_settings

class EncryptionService:
    """
    AES-256-GCM Encryption Service.
    Uses 12-byte nonce (IV) prepended to the ciphertext.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._key = self._load_key()
        self._aesgcm = AESGCM(self._key)

    def _load_key(self) -> bytes:
        """
        Load and decode the 256-bit (32-byte) key.
        Input key in config should be a base64 encoded strings of 32 random bytes.
        """
        key_str = self.settings.encryption_key
        try:
            # If key is provided as hex or direct string, handle appropriately.
            # Assuming standard base64 encoded 32-byte key for safety.
            key_bytes = base64.urlsafe_b64decode(key_str)
            if len(key_bytes) != 32:
                 # Fallback: maybe it's just a raw string, if length is 32 chars? 
                 # But 32 chars is weak entropy if not random bytes.
                 # Let's enforce strictness for "hardening".
                 if len(key_str) == 32: # User provided raw string
                     return key_str.encode()
                 raise ValueError(f"Encryption key must be 32 bytes (256 bits). Got {len(key_bytes)}")
            return key_bytes
        except Exception as e:
            # Attempt to use it directly if decoding failed? 
            # Ideally we crash if key is bad.
            if len(key_str) == 32:
                return key_str.encode()
            raise ValueError(f"Invalid encryption key format: {e}")

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypts plaintext string to base64 encoded ciphertext.
        Format: base64(nonce + ciphertext + tag)
        AESGCM handles the tag automatically in the output.
        """
        if not plaintext:
            return ""
        
        # unique nonce for every encryption
        nonce = os.urandom(12) 
        data = plaintext.encode("utf-8")
        
        ciphertext = self._aesgcm.encrypt(nonce, data, None)
        # Prepend nonce to ciphertext for decryption
        final_payload = nonce + ciphertext
        return base64.urlsafe_b64encode(final_payload).decode("utf-8")

    def decrypt(self, payload: str) -> str:
        """
        Decrypts base64 encoded payload to plaintext string.
        """
        if not payload:
            return ""
            
        try:
            raw_payload = base64.urlsafe_b64decode(payload)
            nonce = raw_payload[:12]
            ciphertext = raw_payload[12:]
            
            decrypted_data = self._aesgcm.decrypt(nonce, ciphertext, None)
            return decrypted_data.decode("utf-8")
        except Exception as e:
            # Log error or re-raise? Re-raising is safer than returning garbage
            raise ValueError(f"Decryption failed: {e}")
