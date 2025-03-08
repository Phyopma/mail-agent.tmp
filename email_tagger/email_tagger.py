"""Email Tagging Agent for Mail Agent.

This module processes LLM analysis results to apply standardized tags
for email priority and category classification.
"""

from typing import Dict, Any, Optional, List
from enum import Enum


class EmailTag(str, Enum):
    """Standardized email tag prefixes."""
    PRIORITY = "Priority"
    CATEGORY = "Category"


class EmailTagger:
    """Handles email tagging based on LLM analysis results."""

    def __init__(self):
        """Initialize the email tagger."""
        self.priority_prefix = f"{EmailTag.PRIORITY.value}/"
        self.category_prefix = f"{EmailTag.CATEGORY.value}/"

    def _normalize_enum_value(self, value: Any) -> str:
        """Normalize enum values to consistent string format.

        Args:
            value: Enum value or string to normalize

        Returns:
            Normalized string value in Title Case
        """
        if value is None:
            return ""

        # Convert to string and handle different formats
        str_value = str(value)

        # If it's in format like "EnumName.VALUE" or contains a dot
        if '.' in str_value:
            str_value = str_value.split('.')[-1]

        # Return in Title Case format (first letter capitalized, rest lowercase)
        return str_value.title()

    def tag_email(self, email_data: Dict[str, Any], analysis_result: Dict[str, Any]) -> Dict[str, Any]:
        """Apply priority and category tags based on LLM analysis.

        Args:
            email_data: Original email data dictionary
            analysis_result: LLM analysis results containing priority and category

        Returns:
            Updated email data with tags
        """
        try:
            # Initialize tags list if not present
            if 'tags' not in email_data:
                email_data['tags'] = []

            # Extract priority and category from analysis
            priority = analysis_result.get('priority')
            category = analysis_result.get('category')

            # Add priority tag if available
            if priority:
                priority_value = self._normalize_enum_value(priority)
                priority_tag = f"{self.priority_prefix}{priority_value}"
                if priority_tag not in email_data['tags']:
                    email_data['tags'].append(priority_tag)
                    print(f"Added priority tag: {priority_tag}")  # Debug log

            # Add category tag if available
            if category:
                category_value = self._normalize_enum_value(category)
                category_tag = f"{self.category_prefix}{category_value}"
                if category_tag not in email_data['tags']:
                    email_data['tags'].append(category_tag)
                    print(f"Added category tag: {category_tag}")  # Debug log

            # Add tagging status
            email_data['tagging_status'] = 'success'

            return email_data

        except Exception as e:
            # Handle tagging errors
            error_data = email_data.copy()
            error_data['tagging_status'] = 'error'
            error_data['error_message'] = str(e)
            print(f"Tagging error: {str(e)}")  # Debug log
            return error_data

    def tag_email_batch(self, email_data_list: List[Dict[str, Any]],
                        analysis_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply tags to multiple emails based on batch analysis results.

        Args:
            email_data_list: List of email data dictionaries
            analysis_results: List of corresponding LLM analysis results

        Returns:
            List of updated email data with tags
        """
        if len(email_data_list) != len(analysis_results):
            raise ValueError(
                "Number of emails must match number of analysis results")

        tagged_emails = []
        for email_data, analysis in zip(email_data_list, analysis_results):
            tagged_email = self.tag_email(email_data, analysis)
            tagged_emails.append(tagged_email)

        return tagged_emails
