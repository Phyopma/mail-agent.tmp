"""Email Preprocessor Module for Mail Agent.

This module handles cleaning and standardizing email content by removing HTML,
extracting text, and preparing the content for LLM processing. It ensures the
output fits within specified length limits while preserving essential information.
"""

from typing import Dict, Any, List, Tuple
from bs4 import BeautifulSoup
import re
import base64
import html
from collections import defaultdict


class EmailPreprocessor:
    """Handles cleaning and standardizing email content."""

    def __init__(self, max_chars: int = 3000):
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
                decoded_content = base64.urlsafe_b64decode(
                    email_data['body'].encode('utf-8')).decode('utf-8')
            else:
                decoded_content = ''

            # Clean the content
            cleaned_text = self._clean_html(decoded_content)
            cleaned_text = self._clean_urls(cleaned_text)
            cleaned_text = self._remove_signatures_and_disclaimers(cleaned_text)
            cleaned_text = self._normalize_whitespace(cleaned_text)
            cleaned_text = self._clean_special_characters(cleaned_text)
            
            # Ensure text fits within max length while preserving context
            cleaned_text = self._limit_text_length(cleaned_text)

            # Update email data with cleaned content
            processed_email = email_data.copy()
            processed_email['cleaned_body'] = cleaned_text
            processed_email['preprocessing_status'] = 'success'

            return processed_email

        except Exception as e:
            # Handle preprocessing errors
            error_email = email_data.copy()
            error_email['preprocessing_status'] = 'error'
            error_email['error_message'] = str(e)
            error_email['cleaned_body'] = ''
            return error_email

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

        # Get text content
        text = soup.get_text(separator=' ')
        return text

    def _clean_urls(self, text: str) -> str:
        """Remove URLs and embedded links from text content.

        Args:
            text: Text content to clean

        Returns:
            Text with URLs removed
        """
        # Remove URLs with common protocols
        text = re.sub(r'https?://\S+|www\.\S+', '', text)

        # Remove remaining URLs (without protocol)
        text = re.sub(
            r'(?:\S+\.)+(?:com|org|net|edu|gov|mil|biz|info|io|ai|co)\S*', '', text)

        # Clean up any remaining artifacts
        text = re.sub(r'\s+', ' ', text)
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

        # Replace multiple whitespace (including newlines and tabs) with single space
        text = re.sub(r'\s+', ' ', text)

        # Remove leading/trailing whitespace
        return text.strip()

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

    def _limit_text_length(self, text: str) -> str:
        """Limit text length while preserving context and important information.

        Args:
            text: Text content to limit

        Returns:
            Text limited to max_chars while preserving context
        """
        if len(text) <= self.max_chars:
            return text

        # Split text into paragraphs
        paragraphs = text.split('\n\n')

        # Calculate importance scores for paragraphs
        scored_paragraphs = []
        for i, para in enumerate(paragraphs):
            score = self._calculate_paragraph_importance(para, i, len(paragraphs))
            scored_paragraphs.append((score, para))

        # Sort paragraphs by importance
        scored_paragraphs.sort(reverse=True)

        # Build final text within length limit
        result = []
        current_length = 0

        for _, para in scored_paragraphs:
            if current_length + len(para) + 2 <= self.max_chars:  # +2 for '\n\n'
                result.append(para)
                current_length += len(para) + 2

        return '\n\n'.join(result)

    def _calculate_paragraph_importance(self, paragraph: str, position: int, total_paragraphs: int) -> float:
        """Calculate importance score for a paragraph based on various factors.

        Args:
            paragraph: Paragraph text
            position: Position in the email (0-based)
            total_paragraphs: Total number of paragraphs

        Returns:
            Importance score (higher is more important)
        """
        score = 0.0

        # Position-based scoring (prioritize start and end of email)
        if position == 0:  # First paragraph
            score += 5.0
        elif position == total_paragraphs - 1:  # Last paragraph
            score += 3.0
        elif position < total_paragraphs * 0.3:  # Early paragraphs
            score += 2.0

        # Content-based scoring
        lower_para = paragraph.lower()
        
        # Check for action items and questions
        if any(word in lower_para for word in ['please', 'action', 'required', 'needed', 'urgent']):
            score += 3.0
        if '?' in paragraph:
            score += 2.0

        # Check for dates and times
        if re.search(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\d{1,2}:\d{2}\b', paragraph):
            score += 2.0

        # Length penalty for very short or very long paragraphs
        para_len = len(paragraph)
        if 50 <= para_len <= 300:
            score += 1.0
        elif para_len > 300:
            score -= (para_len - 300) / 300

        return score

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
