# Vercel serverless entry: /api and /api/
import os
import sys
# Ensure project root is on path so "server" can be imported
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)
from server.main import app
