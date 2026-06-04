import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

_client: Client | None = None


def get_supabase_client() -> Client:
    """Client Supabase partagé (une seule instance par processus)."""
    global _client
    if _client is not None:
        return _client

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL et SUPABASE_KEY sont requis dans le fichier .env")

    _client = create_client(url, key)
    return _client
