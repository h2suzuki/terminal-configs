"""Import shim exposing tests embedded in the extensionless command."""

import importlib.machinery
import os

_path = os.path.join(os.path.dirname(__file__), "claude_court_guard")
_loader = importlib.machinery.SourceFileLoader(__name__, _path)
_loader.exec_module(__import__(__name__))
