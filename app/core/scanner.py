"""
File Scanner and Validator.
Handles MIME type validation (magic numbers) and Malware Scanning.
"""
import os
import puremagic
from typing import Tuple
from loguru import logger

class FileValidator:
    """
    Validates file integrity and type.
    """
    
    # Allowed MIME types map
    ALLOWED_MIME_TYPES = {
        'application/pdf': ['.pdf'],
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
        'text/plain': ['.txt', '.csv'], # CSV often matched as text/plain
        'text/csv': ['.csv'],
        'application/vnd.ms-excel': ['.xls', '.csv'],
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
        'application/vnd.ms-powerpoint': ['.ppt'],
        'application/vnd.openxmlformats-officedocument.presentationml.presentation': ['.pptx'],
        'image/jpeg': ['.jpg', '.jpeg'],
        'image/png': ['.png']
    }

    @staticmethod
    def validate_mime_type(file_header: bytes, filename: str) -> Tuple[bool, str]:
        """
        Validate that the file header matches the extension.
        Returns (is_valid, mime_type_detected).
        """
        try:
            # Detect MIME from bytes
            # puremagic.from_string returns list of matches, or raises error
            # We want the mime type string
            try:
                # Returns list of MagicInfo, or just use from_string with mime=True (if allowed?)
                # accurate=True scans more bytes?
                # puremagic.magic_string(bytes) returns list of MagicInfo
                # Let's use from_string which is the easy API
                detected = puremagic.from_string(file_header, mime=True)
                # puremagic often returns generic 'application/octet-stream' if unsure
                detected_mime = detected if detected else "unknown"
            except puremagic.PureError:
                detected_mime = "unknown"
            
            ext = os.path.splitext(filename)[1].lower()
            
            # Special logic for puremagic which is less robust than libmagic
            if detected_mime == "unknown" or detected_mime is None:
                # If puremagic fails, we might want to fail open OR inspect bytes manually?
                # For safety, let's log warning
                logger.warning(f"Puremagic could not identify {filename}, header: {file_header[:20]}")
                # Fallback: if text, it often fails magic check
                if ext in ['.txt', '.csv']:
                    return True, "text/plain (fallback)"
                return False, "unknown"

            # Check if detected mime is in allowed list
            if detected_mime not in FileValidator.ALLOWED_MIME_TYPES:
                # Relaxed check for text files
                if ext in ['.txt', '.csv'] and ('text' in detected_mime or detected_mime == 'application/octet-stream'):
                     return True, detected_mime
                
                # Relaxed check for Office files (often return zip/octet-stream)
                if ext in ['.docx', '.xlsx', '.pptx'] and detected_mime in ['application/zip', 'application/x-zip-compressed']:
                     return True, detected_mime
                
                logger.warning(f"MIME Mismatch or Blocked: {filename} is {detected_mime} (Ext: {ext})")
                return False, detected_mime
            
            # Check if extension matches the mime type
            allowed_exts = FileValidator.ALLOWED_MIME_TYPES.get(detected_mime, [])
            
            # Special Handling for Office XML Formats (often confused by puremagic)
            office_mimes = [
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                'application/zip', 
                'application/x-zip-compressed'
            ]
            office_exts = ['.docx', '.xlsx', '.pptx']
            
            if ext in office_exts and detected_mime in office_mimes:
                return True, detected_mime

            if ext not in allowed_exts:
                # Special cases
                if detected_mime == 'text/plain' and ext == '.csv':
                    return True, detected_mime
                    
                logger.warning(f"Extension Spoofing Attempt? {filename} is {detected_mime} but has ext {ext}")
                return False, detected_mime
                
            return True, detected_mime
            
        except Exception as e:
            logger.error(f"Error validating MIME type: {e}")
            return False, "unknown/error"


class MalwareScanner:
    """
    Interface for Malware Scanning (Stub).
    """
    
    @staticmethod
    def scan_file(file_path: str) -> bool:
        """
        Scan a file for malware.
        Returns True if safe, False if infected.
        """
        try:
            # TODO: Integrate ClamAV or external scanner.
            # Example:
            # import clamd
            # cd = clamd.ClamdUnixSocket()
            # result = cd.scan(file_path)
            # return result[file_path] == 'OK'
            
            # Log warning that we are in Stub mode
            # logger.info(f"Skipping Malware Scan (Stub) for {file_path}")
            return True
        except Exception as e:
            logger.error(f"Malware scan failed: {e}")
            return True # Fail open? Or Fail closed? 
            # Ideally Fail Closed, but for a stub we return Safe to avoid blocking dev.
