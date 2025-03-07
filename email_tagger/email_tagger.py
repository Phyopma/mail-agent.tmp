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
                # Format priority tag to match exactly with Gmail label format
                # Extract just the value part if it's in format like EmailPriority.LOW
                if '.' in str(priority):
                    priority_value = str(priority).split('.')[-1].capitalize()
                else:
                    priority_value = str(priority).capitalize()
                priority_tag = f"{self.priority_prefix}{priority_value}"
                if priority_tag not in email_data['tags']:
                    email_data['tags'].append(priority_tag)

            # Add category tag if available
            if category:
                # Format category tag to match exactly with Gmail label format
                # Extract just the value part if it's in format like EmailCategory.MARKETING
                if '.' in str(category):
                    category_value = str(category).split('.')[-1].capitalize()
                else:
                    category_value = str(category).capitalize()
                category_tag = f"{self.category_prefix}{category_value}"
                if category_tag not in email_data['tags']:
                    email_data['tags'].append(category_tag)

            # Add tagging status
            email_data['tagging_status'] = 'success'

            return email_data

        except Exception as e:
            # Handle tagging errors
            error_data = email_data.copy()
            error_data['tagging_status'] = 'error'
            error_data['error_message'] = str(e)
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
