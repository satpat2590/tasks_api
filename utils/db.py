"""Shared Supabase client for Atma.

A single client instance is created here and reused across the app (main.py)
and the tag pipeline (utils/tags.py) so we don't hold two independent
connections to the same backend.
"""

import os

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ACCESS_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_API_KEY")

if not SUPABASE_URL or not SUPABASE_ACCESS_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY or SUPABASE_API_KEY must be set")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ACCESS_KEY)
