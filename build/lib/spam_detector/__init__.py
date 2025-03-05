"""Spam Detection Module.

This module provides functionality for detecting spam emails using LLM-based analysis.
"""

# from .spam_detector import SpamDetector
from .spam_detector import UnifiedEmailAnalyzer, ToolAction

__all__ = ['UnifiedEmailAnalyzer', 'ToolAction']
