"""Local JSON runtime state repository adapter.

Runtime state controls idempotency, so this adapter will use atomic writes once
the storage implementation is added.
"""
