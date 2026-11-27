"""One-off data migrations that need to be re-runnable.

Alembic handles schema. These scripts move rows between shapes and report what
they did, so a large backfill can be stopped, inspected, and resumed.
"""
