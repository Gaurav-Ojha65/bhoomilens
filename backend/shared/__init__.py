"""Shared logic used by every BhoomiLens Lambda.

Kept dependency-light so it imports cleanly inside every Lambda layer.
No boto3 calls at import time — resource wiring belongs to each handler.
"""
