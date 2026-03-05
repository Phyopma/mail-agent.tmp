"""Email Preprocessor Module for Mail Agent.

This module handles cleaning and standardizing email content by removing HTML,
extracting text, and preparing the content for LLM processing. It ensures the
output fits within specified length limits while preserving essential information.
"""

from typing import Dict, Any, Tuple
from bs4 import BeautifulSoup
import re
import base64
import html


class EmailPreprocessor:
    """Handles cleaning and standardizing email content."""

    def __init__(self, max_chars: int = 6000):
        self.html_parser = 'html.parser'
        self.max_chars = max_chars
        self.common_signatures = [
            r'Best regards',
            r'Kind regards',
            r'Regards',
            r'Thanks',
            r'Sincerely',
            r'Cheers',
            r'\s*--+\s*',  # Signature separator
            r'Sent from my \w+',  # Mobile signatures
            r'Get Outlook for \w+',  # Email client signatures
        ]
        self.disclaimer_patterns = [
            r'CONFIDENTIALITY NOTICE',
            r'DISCLAIMER',
            r'This email and any files transmitted with it',
            r'This message contains confidential information',
            r'This email is intended only for',
        ]

    def preprocess_email(self, email_data: Dict[str, Any]) -> Dict[str, Any]:
        """Clean and standardize email content.

        Args:
            email_data: Dictionary containing email data with at least 'body' field

        Returns:
            Dictionary with cleaned email content and metadata
        """
        try:
            # Decode base64 content if present
            if email_data.get('body'):
                decoded_content = self._safe_decode_body(email_data['body'])
            else:
                decoded_content = ''
            extraction_source = self._infer_extraction_source(decoded_content, email_data)

            # Clean the content
            cleaned_text = self._clean_html(decoded_content)
            cleaned_text, has_reply_chain = self._strip_quoted_reply_blocks(cleaned_text)
            cleaned_text = self._clean_urls(cleaned_text)
            cleaned_text = self._remove_signatures_and_disclaimers(
                cleaned_text)
            cleaned_text = self._normalize_whitespace(cleaned_text)
            cleaned_text = self._clean_special_characters(cleaned_text)
            cleaned_text = cleaned_text[: self.max_chars]
            text_length = len(cleaned_text)
            body_quality = self._classify_body_quality(text_length)

            # Update email data with cleaned content
            processed_email = email_data.copy()
            processed_email['cleaned_body'] = cleaned_text
            processed_email['text_length'] = text_length
            processed_email['body_quality'] = body_quality
            processed_email['preprocessing_status'] = 'success'
            processed_email['extraction_source'] = extraction_source
            processed_email['has_reply_chain'] = has_reply_chain

            return processed_email

        except Exception as e:
            # Handle preprocessing errors
            error_email = email_data.copy()
            error_email['preprocessing_status'] = 'error'
            error_email['error_message'] = str(e)
            error_email['cleaned_body'] = ''
            error_email['text_length'] = 0
            error_email['body_quality'] = 'no_text'
            error_email['extraction_source'] = 'none'
            error_email['has_reply_chain'] = False
            return error_email

    def _infer_extraction_source(self, decoded_content: str, email_data: Dict[str, Any]) -> str:
        source = str(email_data.get("extraction_source") or "").strip().lower()
        if source in {"text_plain", "text_html", "mixed", "none"}:
            return source
        if not decoded_content.strip():
            return "none"
        lowered = decoded_content.lower()
        if "<html" in lowered or "<body" in lowered or re.search(r"<[^>]+>", lowered):
            return "text_html"
        return "text_plain"

    def _safe_decode_body(self, body: str) -> str:
        """Decode Gmail body data using urlsafe base64 with robust fallbacks."""
        if not body:
            return ''

        try:
            padded_body = body + "=" * (-len(body) % 4)
            decoded = base64.urlsafe_b64decode(padded_body.encode('utf-8'))
            return decoded.decode('utf-8', errors='replace')
        except Exception:
            # If the input is not valid base64, treat it as plain text.
            return str(body)

    def _classify_body_quality(self, text_length: int) -> str:
        """Classify content quality for downstream analyzer fallback logic."""
        if text_length == 0:
            return "no_text"
        if text_length < 80:
            return "short_text"
        return "full_text"

    def _clean_html(self, content: str) -> str:
        """Remove HTML tags and extract text content.

        Args:
            content: Raw email content with potential HTML

        Returns:
            Clean text content
        """
        # Unescape HTML entities
        content = html.unescape(content)

        # Parse HTML and extract text
        soup = BeautifulSoup(content, self.html_parser)

        # Remove script and style elements
        for element in soup(['script', 'style']):
            element.decompose()

        # Get text content while preserving line boundaries for downstream heuristics.
        text = soup.get_text(separator='\n')
        return text

    def _clean_urls(self, text: str) -> str:
        """Remove URLs and embedded links from text content.

        Args:
            text: Text content to clean

        Returns:
            Text with URLs removed
        """
        # Replace URLs with placeholders so the analyzer keeps "link present" signal.
        text = re.sub(r'https?://\S+|www\.\S+', ' [URL] ', text)
        text = re.sub(
            r'(?:\S+\.)+(?:com|org|net|edu|gov|mil|biz|info|io|ai|co)\S*',
            ' [URL] ',
            text,
        )
        text = re.sub(r'(?:\s*\[URL\]\s*){2,}', ' [URL] ', text)
        return text.strip()

    def _normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace in text.

        Args:
            text: Text content to normalize

        Returns:
            Text with normalized whitespace
        """
        # Remove special Unicode whitespace characters
        text = re.sub(
            r'[\u034f\u2800\u2000-\u200F\u2028-\u202F\u205F-\u206F\u3000\uFEFF]', '', text)

        # Normalize line endings and collapse horizontal whitespace without flattening lines.
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        text = re.sub(r'[ \t]+', ' ', text)

        # Trim every line and collapse extra blank lines.
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(lines)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _strip_quoted_reply_blocks(self, text: str) -> Tuple[str, bool]:
        """Remove quoted reply chain content while preserving current-message text."""
        if not text:
            return text, False

        lines = text.split('\n')
        stop_patterns = [
            r'^\s*On .+wrote:\s*$',
            r'^\s*-----\s*Original Message\s*-----\s*$',
            r'^\s*From:\s?.+@.+$',
        ]

        cutoff_index = None
        for idx, line in enumerate(lines):
            if any(re.search(pattern, line, re.IGNORECASE) for pattern in stop_patterns):
                cutoff_index = idx
                break
            # Some HTML-to-text conversions split "On ... wrote:" across lines.
            if re.search(r'^\s*On .+$', line, re.IGNORECASE):
                next_line = lines[idx + 1] if idx + 1 < len(lines) else ""
                if re.search(r'^\s*wrote:\s*$', next_line, re.IGNORECASE):
                    cutoff_index = idx
                    break

        has_reply_chain = cutoff_index is not None
        working_lines = lines[:cutoff_index] if cutoff_index is not None else lines
        filtered_lines = []
        for line in working_lines:
            if line.strip().startswith('>'):
                has_reply_chain = True
                continue
            filtered_lines.append(line)

        return '\n'.join(filtered_lines), has_reply_chain

    def _remove_signatures_and_disclaimers(self, text: str) -> str:
        """Remove email signatures and legal disclaimers.

        Args:
            text: Text content to clean

        Returns:
            Text with signatures and disclaimers removed
        """
        # Split text into lines for processing
        lines = text.split('\n')
        filtered_lines = []
        skip_section = False

        for line in lines:
            # Check if line starts a disclaimer section
            if any(re.search(pattern, line, re.IGNORECASE) for pattern in self.disclaimer_patterns):
                skip_section = True
                continue

            # Check if line is part of a signature
            if any(re.search(pattern, line, re.IGNORECASE) for pattern in self.common_signatures):
                continue

            if not skip_section:
                filtered_lines.append(line)

        return '\n'.join(filtered_lines)

    def _clean_special_characters(self, text: str) -> str:
        """Clean special characters and emojis while preserving essential punctuation.

        Args:
            text: Text content to clean

        Returns:
            Cleaned text content with emojis removed
        """
        # Define emoji pattern covering all Unicode emoji ranges
        emoji_pattern = re.compile("["
                                   "\U0001F600-\U0001F64F"  # emoticons
                                   "\U0001F300-\U0001F5FF"  # symbols & pictographs
                                   "\U0001F680-\U0001F6FF"  # transport & map symbols
                                   "\U0001F1E0-\U0001F1FF"  # flags (iOS)
                                   "\U00002702-\U000027B0"  # dingbats
                                   "\U000024C2-\U0001F251"  # enclosed characters
                                   "\U0001F900-\U0001F9FF"  # supplemental symbols
                                   "\U0001FA70-\U0001FAFF"  # symbols & pictographs extended-A
                                   "\u200d"                  # zero width joiner
                                   "\u2640-\u2642"          # gender symbols
                                   "\u2600-\u2B55"          # miscellaneous symbols
                                   "\u23cf"                  # directional icons
                                   "\u23e9"                  # play/pause symbols
                                   "\u231a-\u231b"          # watch symbols
                                   "\u25aa-\u25ab"          # geometric shapes
                                   "\u2934-\u2935"          # arrows
                                   "]", re.UNICODE)

        # Remove emojis
        text = emoji_pattern.sub('', text)

        # Remove control characters except newlines
        text = ''.join(
            char for char in text if char.isprintable() or char == '\n')

        # Normalize newlines
        text = re.sub(r'\n\s*\n+', '\n\n', text)
        return text.strip()
