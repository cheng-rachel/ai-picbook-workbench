"""Local teacher-facing Web App (M6). Thin view layer over backend workflows."""

from .server import create_server

__all__ = ["create_server"]
