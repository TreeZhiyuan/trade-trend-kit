"""Scheduler entry points.

The scheduler will stay thin: it should trigger application services, not hold
business logic itself. That keeps scheduled and one-shot execution consistent.
"""
