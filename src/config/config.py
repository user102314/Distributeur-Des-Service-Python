import json
import os
from dotenv import load_dotenv

# Force le chargement du fichier .env
load_dotenv()


def _build_tts_voice_map() -> dict:
    """Voix neuronales Azure par défaut selon locale (BCP‑47 ou code court). À surcharger avec AZURE_TTS_VOICE_BY_LOCALE (JSON)."""
    defaults = {
        "ar-sa": "ar-SA-HamedNeural",
        "ar": "ar-SA-HamedNeural",
        "fr-fr": "fr-FR-HenriNeural",
        "fr": "fr-FR-HenriNeural",
        "en-us": "en-US-GuyNeural",
        "en-gb": "en-GB-RyanNeural",
        "en": "en-US-GuyNeural",
    }
    raw = os.getenv("AZURE_TTS_VOICE_BY_LOCALE", "").strip()
    if not raw:
        return defaults
    try:
        custom = json.loads(raw)
        for k, v in custom.items():
            if isinstance(k, str) and isinstance(v, str) and k.strip():
                defaults[k.strip().lower()] = v.strip()
    except json.JSONDecodeError:
        pass
    return defaults


class Settings:
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY")
    AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION")
    AZURE_SPEECH_VOICE = os.getenv("AZURE_SPEECH_VOICE", "ar-SA-HamedNeural")
    AZURE_SPEECH_RECOGNITION_LANGUAGE = os.getenv("AZURE_SPEECH_RECOGNITION_LANGUAGE", "ar-SA")

    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    GEMINI_TIMEOUT_SECONDS = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "60"))
    GEMINI_MAX_RETRIES = int(os.getenv("GEMINI_MAX_RETRIES", "3"))

    FFMPEG_PATH = os.getenv("FFMPEG_PATH")


_TTS_VOICE_MAP = _build_tts_voice_map()

settings = Settings()


def resolve_tts_voice_for_bcp47_locale(locale: str, fallback_voice: str) -> str:
    """Retourne la voix Neural Azure correspondant à la langue/locale du robot (audio finale = même langue que setting.langue)."""
    if not locale or not locale.strip():
        return fallback_voice
    key_full = locale.strip().lower()
    if key_full in _TTS_VOICE_MAP:
        return _TTS_VOICE_MAP[key_full]
    primary = key_full.split("-")[0]
    if primary in _TTS_VOICE_MAP:
        return _TTS_VOICE_MAP[primary]
    return fallback_voice


if not settings.SUPABASE_URL:
    print("❌ Erreur : SUPABASE_URL est introuvable dans les variables d'environnement")
