"""Deprecated spam detector module.

This module is kept for backward compatibility. Use
spam_detector.unified_email_analyzer.UnifiedEmailAnalyzer instead.
"""

from .unified_email_analyzer import (  # noqa: F401
    UnifiedEmailAnalyzer,
    EmailAnalysisResult,
    EmailCategory,
    EmailPriority,
    Spam,
    ToolAction,
    CalendarEvent,
    Reminder,
    Task,
)

__all__ = [
    "UnifiedEmailAnalyzer",
    "EmailAnalysisResult",
    "EmailCategory",
    "EmailPriority",
    "Spam",
    "ToolAction",
    "CalendarEvent",
    "Reminder",
    "Task",
]
