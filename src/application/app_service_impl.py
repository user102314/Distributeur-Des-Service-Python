import io
import os
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path
import wave
import httpx
import json
from datetime import datetime
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
from src.presentation.services_interfaces import IApiService
from src.infrastructure.database import get_supabase_client
from src.infrastructure.n8n_client import N8NClient
from src.infrastructure.safe_console import safe_console_line
from src.infrastructure.gemini_client import GeminiClient
from src.config.config import resolve_tts_voice_for_bcp47_locale, settings

try:
    import azure.cognitiveservices.speech as speechsdk
    AZURE_SPEECH_AVAILABLE = True
except ImportError:
    AZURE_SPEECH_AVAILABLE = False

try:
    import face_recognition
    import numpy as np
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False


class ApiServiceImpl(IApiService):
    def __init__(self):
        self.client = get_supabase_client()
        self.n8n = N8NClient()
        self.gemini = GeminiClient()
        self._known_faces_cache = []
        self._known_faces_cache_at = 0.0
        self._known_faces_ttl_seconds = 300
        self._cache_lock = threading.Lock()
        self._is_refreshing_faces = False

    # --- UTILISATEURS ---
    def get_all_users(self):
        return self.client.table("utilisateur").select("*").execute().data

    def get_user(self, iduser: int):
        res = self.client.table("utilisateur").select("*").eq("iduser", iduser).execute().data
        return res[0] if res else None

    def create_user(self, data: dict):
        return self.client.table("utilisateur").insert(data).execute().data

    def update_user(self, iduser: int, data: dict):
        return self.client.table("utilisateur").update(data).eq("iduser", iduser).execute().data

    def delete_user(self, iduser: int):
        return self.client.table("utilisateur").delete().eq("iduser", iduser).execute().data

    # --- IMAGES UTILISATEUR (table imageuser) ---
    def get_all_user_images(self):
        return self.client.table("imageuser").select("*").execute().data

    def get_user_image(self, idimage: int):
        res = self.client.table("imageuser").select("*").eq("idimage", idimage).execute().data
        return res[0] if res else None

    def get_user_images_by_user(self, iduser: int):
        return self.client.table("imageuser").select("*").eq("iduser", iduser).execute().data

    def create_user_image(self, data: dict):
        row = self.client.table("imageuser").insert(self._fix_booleans(data)).execute().data
        self._invalidate_known_faces_cache()
        return row

    def update_user_image(self, idimage: int, data: dict):
        row = self.client.table("imageuser").update(self._fix_booleans(data)).eq("idimage", idimage).execute().data
        self._invalidate_known_faces_cache()
        return row

    def delete_user_image(self, idimage: int):
        row = self.client.table("imageuser").delete().eq("idimage", idimage).execute().data
        self._invalidate_known_faces_cache()
        return row

    # --- HISTORIQUE ---
    def get_all_history(self):
        return self.client.table("historique").select("*").order("created_at", desc=True).execute().data

    def get_historique(self, historique_id: int):
        res = self.client.table("historique").select("*").eq("id", historique_id).execute().data
        return res[0] if res else None

    def create_historique(self, data: dict):
        return self.client.table("historique").insert(self._fix_booleans(data)).execute().data

    def delete_historique(self, historique_id: int):
        return self.client.table("historique").delete().eq("id", historique_id).execute().data

    # --- CONVERSATIONS ---
    @staticmethod
    def _normalize_conversation_row(row: dict) -> dict:
        if row.get("idconv") is None and row.get("id") is not None:
            row["idconv"] = row["id"]
        raw = row.get("date")
        if raw is not None:
            if isinstance(raw, str):
                row["date"] = raw.split("T")[0][:10]
            else:
                row["date"] = str(raw)[:10]
        return row

    def get_last_100_conversations(self):
        rows = self.client.table("conversation").select("*").order("date", desc=True).limit(100).execute().data or []
        return [self._normalize_conversation_row(row) for row in rows]

    def get_all_conversations(self, date_from=None, date_to=None):
        try:
            query = self.client.table("conversation").select("*")
            if date_from is not None:
                d0 = date_from.date().isoformat() if hasattr(date_from, "date") else str(date_from)[:10]
                query = query.gte("date", d0)
            if date_to is not None:
                d1 = date_to.date().isoformat() if hasattr(date_to, "date") else str(date_to)[:10]
                query = query.lte("date", d1)
            rows = query.order("date", desc=True).execute().data or []
            return [self._normalize_conversation_row(row) for row in rows]
        except Exception as exc:
            safe_console_line(f"[conversation] get_all_conversations: {exc}")
            return self.get_last_100_conversations()

    def get_conversation(self, idconv: int):
        res = self.client.table("conversation").select("*").eq("idconv", idconv).execute().data
        return res[0] if res else None

    def create_conversation(self, data: dict):
        return self.client.table("conversation").insert(self._fix_booleans(data)).execute().data

    def update_conversation(self, idconv: int, data: dict):
        return self.client.table("conversation").update(self._fix_booleans(data)).eq("idconv", idconv).execute().data

    def delete_conversation(self, idconv: int):
        return self.client.table("conversation").delete().eq("idconv", idconv).execute().data

    # --- NOTES ---
    def get_all_notes(self):
        return self.client.table("note").select("*").order("id", desc=True).execute().data

    def get_note(self, note_id: int):
        res = self.client.table("note").select("*").eq("id", note_id).execute().data
        return res[0] if res else None

    def create_note(self, data: dict):
        return self.client.table("note").insert(self._fix_booleans(data)).execute().data

    def update_note(self, note_id: int, data: dict):
        return self.client.table("note").update(self._fix_booleans(data)).eq("id", note_id).execute().data

    def delete_note(self, note_id: int):
        return self.client.table("note").delete().eq("id", note_id).execute().data

    def modify_note_etat(self, note_id: int, etat: bool):
        val = 1 if etat else 0
        return self.client.table("note").update({"etat": val}).eq("id", note_id).execute().data

    # --- SETTINGS ---
    def _primary_setting_idkoda(self) -> Optional[str]:
        """Clé primaire de la ligne setting (colonne idkoda)."""
        res = self.client.table("setting").select("idkoda").limit(1).execute().data
        if not res:
            return None
        v = res[0].get("idkoda")
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    def get_settings(self):
        res = self.client.table("setting").select("*").limit(1).execute().data
        return res[0] if res else None

    def modify_settings(self, settings_data: dict):
        fixed_data = self._fix_booleans(settings_data)
        idkoda = self._primary_setting_idkoda()
        if not idkoda:
            return None
        return self.client.table("setting").update(fixed_data).eq("idkoda", idkoda).execute().data

    def _get_robot_langue_from_setting(self):
        """Locale BCP‑47 ou identifiant de langue (ex. ar-SA, fr-FR) stockée dans setting.langue."""
        try:
            res = self.client.table("setting").select("langue").limit(1).execute().data
        except Exception:
            return None
        if not res:
            return None
        val = res[0].get("langue")
        if val is None:
            return None
        s = str(val).strip()
        return s if s else None

    @staticmethod
    def _canonical_locale_for_speech_and_translation(raw: Optional[str]) -> str:
        """
        Azure Speech STT attend une locale BCP-47 (ex. ar-SA), pas un nom de voix TTS (ex. ar-SA-HamedNeural).
        Erreur 1007 / language invalide si la colonne langue contient une voix Neural.
        """
        fb = settings.AZURE_SPEECH_RECOGNITION_LANGUAGE
        if not raw or not str(raw).strip():
            return fb
        parts = [p for p in str(raw).strip().replace("_", "-").split("-") if p]
        if not parts:
            return fb
        if len(parts) >= 3 and parts[-1].lower().endswith("neural"):
            return f"{parts[0].lower()}-{parts[1].upper()}"
        if len(parts) == 2 and len(parts[0]) >= 2 and len(parts[1]) >= 2:
            return f"{parts[0].lower()}-{parts[1].upper()}"
        if len(parts) == 1 and len(parts[0]) == 2:
            short = parts[0].lower()
            default_region = {"ar": "ar-SA", "fr": "fr-FR", "en": "en-US", "es": "es-ES"}
            return default_region.get(short, fb)
        return fb

    # --- INFOS PERSONNELLES ---
    def get_personal_info(self):
        return self.client.table("information_personelle").select("*").execute().data

    def get_personal_info_by_user(self, iduser: int):
        return self.client.table("information_personelle").select("*").eq("iduser", iduser).execute().data

    def add_personal_info(self, info_data: dict):
        return self.client.table("information_personelle").insert(self._fix_booleans(info_data)).execute().data

    def update_personal_info(self, info_id: int, data: dict):
        return self.client.table("information_personelle").update(self._fix_booleans(data)).eq("id", info_id).execute().data

    def delete_personal_info(self, info_id: int):
        return self.client.table("information_personelle").delete().eq("id", info_id).execute().data

    # --- ACCOMPAGNEMENT ---
    def get_all_accompagnements(self):
        return self.client.table("accompagnement").select("*").order("id", desc=True).execute().data

    def get_accompagnement(self, accompagnement_id: int):
        res = self.client.table("accompagnement").select("*").eq("id", accompagnement_id).execute().data
        return res[0] if res else None

    def get_accompagnements_by_user(self, iduser: int):
        return self.client.table("accompagnement").select("*").eq("iduser", iduser).execute().data

    def create_accompagnement(self, data: dict):
        return self.client.table("accompagnement").insert(self._fix_booleans(data)).execute().data

    def update_accompagnement(self, accompagnement_id: int, data: dict):
        return self.client.table("accompagnement").update(self._fix_booleans(data)).eq("id", accompagnement_id).execute().data

    def delete_accompagnement(self, accompagnement_id: int):
        return self.client.table("accompagnement").delete().eq("id", accompagnement_id).execute().data

    # --- AUTHENTIFICATION ---
    def login(self, emailclient: str, motdepasse: str):
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                res = (
                    self.client.table("authentification")
                    .select("*")
                    .eq("emailclient", emailclient)
                    .limit(1)
                    .execute()
                    .data
                )
                break
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError) as exc:
                last_error = exc
                safe_console_line(f"[auth] Supabase tentative {attempt + 1}/2: {exc}")
                if attempt == 0:
                    time.sleep(1)
                    continue
                raise
        else:
            if last_error:
                raise last_error
            res = []
        if not res:
            return None
        row = res[0]
        stored = str(row.get("motdepasse", ""))
        if not secrets.compare_digest(stored, str(motdepasse)):
            return None
        return {
            "idproduit": row.get("idproduit"),
            "emailclient": row.get("emailclient"),
            "idkoda": row.get("idkoda"),
        }

    def get_authentification(self, idproduit: int):
        res = self.client.table("authentification").select("*").eq("idproduit", idproduit).execute().data
        return res[0] if res else None

    def list_authentifications(self):
        return self.client.table("authentification").select("*").execute().data

    def create_authentification(self, data: dict):
        return self.client.table("authentification").insert(self._fix_booleans(data)).execute().data

    def update_authentification(self, idproduit: int, data: dict):
        return self.client.table("authentification").update(self._fix_booleans(data)).eq("idproduit", idproduit).execute().data

    def delete_authentification(self, idproduit: int):
        return self.client.table("authentification").delete().eq("idproduit", idproduit).execute().data

    # --- INTEGRATION N8N ---
    def send_to_n8n(self, payload: dict):
        return self.n8n.trigger_workflow(payload)

    def send_nom_to_webhook(self, nom: str):
        return self.n8n.trigger_nom_webhook(nom)

    # =========================================================
    # --- SMART NOTES (Mappé sur la table 'note') ---
    # =========================================================
    def get_all_activities(self):
        # On utilise la table 'note' qui existe déjà
        return self.client.table("note").select("*").order("id", desc=True).execute().data

    def get_activity(self, activity_id: int):
        res = self.client.table("note").select("*").eq("id", activity_id).execute().data
        return res[0] if res else None

    def create_activity(self, data: dict):
        note_text = data.get("note", data.get("description", ""))
        payload = {
            "note": note_text,
            "etat": 1 if data.get("etat", False) else 0,
        }
        if data.get("date") is not None:
            payload["date"] = data["date"]
        return self.client.table("note").insert(self._fix_booleans(payload)).execute().data

    def update_activity(self, activity_id: int, data: dict):
        payload = self._fix_booleans(data.copy())
        if "description" in payload:
            payload["note"] = payload.pop("description")
        return self.client.table("note").update(payload).eq("id", activity_id).execute().data

    def delete_activity(self, activity_id: int):
        return self.client.table("note").delete().eq("id", activity_id).execute().data

    # =========================================================
    # --- RECONNAISSANCE FACIALE ---
    # =========================================================
    def identify_face(self, image_bytes: bytes) -> str:
        if not FACE_RECOGNITION_AVAILABLE:
            raise RuntimeError("La bibliothèque face_recognition n'est pas installée.")

        input_image = face_recognition.load_image_file(io.BytesIO(image_bytes))
        input_image = self._resize_image_for_speed(input_image, max_width=800)
        input_locations = face_recognition.face_locations(input_image, model="hog")
        input_encodings = face_recognition.face_encodings(input_image, known_face_locations=input_locations, num_jitters=1)
        if not input_encodings:
            return "inconnu"

        known_faces = self._get_known_faces()
        if not known_faces:
            return "inconnu"

        known_encodings = [item["encoding"] for item in known_faces]
        best_name = "inconnu"
        best_distance = 1.0
        tolerance = 0.50

        # Compare chaque visage détecté dans l'image d'entrée avec tous les utilisateurs connus.
        for input_encoding in input_encodings:
            distances = face_recognition.face_distance(known_encodings, input_encoding)
            if len(distances) == 0:
                continue
            best_idx = int(np.argmin(distances))
            current_distance = float(distances[best_idx])
            if current_distance < best_distance:
                best_distance = current_distance
                best_name = known_faces[best_idx]["nom"]

        if best_distance <= tolerance:
            return best_name
        return "inconnu"

    # =========================================================
    # --- POWER ON / OFF ---
    # =========================================================
    def power_off(self):
        idkoda = self._primary_setting_idkoda()
        if idkoda:
            self.client.table("setting").update({"etat": 0}).eq("idkoda", idkoda).execute()
        return {"status": "power_off", "etat": 0}

    def power_on(self):
        idkoda = self._primary_setting_idkoda()
        if idkoda:
            self.client.table("setting").update({"etat": 1}).eq("idkoda", idkoda).execute()
        return {"status": "power_on", "etat": 1}

    # =========================================================
    # --- AUDIO (AZURE SPEECH) ---
    # =========================================================
    @staticmethod
    def _closed_push_stream_raw_pcm(pcm_data: bytes, sample_rate: int, channels: int, bits_per_sample: int):
        stream_format = speechsdk.audio.AudioStreamFormat(
            samples_per_second=sample_rate,
            bits_per_sample=bits_per_sample,
            channels=channels,
        )
        push_stream = speechsdk.audio.PushAudioInputStream(stream_format=stream_format)
        push_stream.write(pcm_data)
        push_stream.close()
        return push_stream

    def _resolve_ffmpeg_executable(self):
        """PATH pas encore à jour après winget → essai lien WinGet + FFMPEG_PATH dans .env."""
        if getattr(settings, "FFMPEG_PATH", None):
            configured = Path(settings.FFMPEG_PATH.strip().strip('"'))
            if configured.is_file():
                return str(configured)
        found = shutil.which("ffmpeg")
        if found:
            return found
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            winget_link = Path(local) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe"
            if winget_link.is_file():
                return str(winget_link)
        return None

    def _transcode_to_raw_s16le_mono_16k_via_ffmpeg(self, audio_bytes: bytes):
        """
        Contourne SPXERR_GSTREAMER_NOT_FOUND_ERROR : Azure reçoit uniquement du PCM linéaire brut,
        sans décodeur conteneur côté SDK (pas de GStreamer sous Windows).
        """
        ffmpeg = self._resolve_ffmpeg_executable()
        if not ffmpeg:
            return None
        in_path = out_path = None
        try:
            fd_in, in_path = tempfile.mkstemp(suffix=".bin")
            os.close(fd_in)
            fd_out, out_path = tempfile.mkstemp(suffix=".raw")
            os.close(fd_out)
            with open(in_path, "wb") as f:
                f.write(audio_bytes)
            subprocess.run(
                [
                    ffmpeg,
                    "-nostdin",
                    "-nostats",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    in_path,
                    "-vn",
                    "-f",
                    "s16le",
                    "-acodec",
                    "pcm_s16le",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    out_path,
                ],
                check=True,
                timeout=120,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            with open(out_path, "rb") as f:
                return f.read()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, FileNotFoundError):
            return None
        finally:
            for p in (in_path, out_path):
                if p:
                    try:
                        os.unlink(p)
                    except OSError:
                        pass

    def _try_push_stream_pcm_wav(self, audio_bytes: bytes):
        """
        PCM linéaire 8 ou 16 bits uniquement (évite le WAV float 32 bits pris pour du PCM brut).
        Ne pas utiliser AudioStreamContainerFormat.ANY sur Windows sans GStreamer.
        """
        try:
            buf = io.BytesIO(audio_bytes)
            with wave.open(buf, "rb") as wf:
                if wf.getcomptype() != "NONE":
                    return None
                channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                sample_rate = wf.getframerate()
                if channels < 1 or sample_width not in (1, 2):
                    return None
                pcm_data = wf.readframes(wf.getnframes())
        except (wave.Error, EOFError):
            return None

        return self._closed_push_stream_raw_pcm(
            pcm_data, sample_rate, channels, sample_width * 8
        )

    def speech_to_text(self, audio_bytes: bytes):
        if not AZURE_SPEECH_AVAILABLE:
            raise RuntimeError("La bibliothèque azure-cognitiveservices-speech n'est pas installée.")
        self._validate_azure_speech_config()

        speech_config = speechsdk.SpeechConfig(
            subscription=settings.AZURE_SPEECH_KEY,
            region=settings.AZURE_SPEECH_REGION
        )
        langue_brute_setting = self._get_robot_langue_from_setting()
        recognition_lang = self._canonical_locale_for_speech_and_translation(
            langue_brute_setting
        )
        safe_console_line("--- Speech-to-Text (service Azure) ---")
        safe_console_line(
            f"Langue lue depuis la table setting.langue : {langue_brute_setting!s}"
        )
        safe_console_line(
            f"Langue utilisee pour la reconnaissance Azure (normalisee) : {recognition_lang}"
        )
        speech_config.speech_recognition_language = recognition_lang

        push_stream = self._try_push_stream_pcm_wav(audio_bytes)
        if push_stream is None:
            raw_pcm = self._transcode_to_raw_s16le_mono_16k_via_ffmpeg(audio_bytes)
            if raw_pcm:
                push_stream = self._closed_push_stream_raw_pcm(raw_pcm, 16000, 1, 16)
        if push_stream is None:
            hint = (
                "FFmpeg introuvable : redémarre le terminal après winget (PATH), ou définit FFMPEG_PATH dans .env "
                "(chemin vers ffmpeg.exe, ex. …\\WinGet\\Links\\ffmpeg.exe), ou exporte un WAV PCM 16 bit. "
                "Réf. erreur SDK : SPXERR_GSTREAMER_NOT_FOUND_ERROR sous Windows sans décodage FFmpeg."
            )
            raise RuntimeError(hint)

        result = None
        audio_config = speechsdk.audio.AudioConfig(stream=push_stream)
        recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
        result = recognizer.recognize_once_async().get()

        if result is None:
            raise RuntimeError("Échec Speech-to-Text (aucun résultat du recognizer).")

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            safe_console_line(f"Convertir la voix en texte : {result.text.strip()}")
            return {
                "text": result.text,
                "status": "success"
            }

        if result.reason == speechsdk.ResultReason.NoMatch:
            return {
                "text": "",
                "status": "no_match"
            }

        if result.reason == speechsdk.ResultReason.Canceled:
            details = result.cancellation_details
            error_message = f"Erreur de reconnaissance: {details.reason}"
            if details.reason == speechsdk.CancellationReason.Error and details.error_details:
                error_message = f"{error_message} - {details.error_details}"
                if "1007" in details.error_details or "language" in details.error_details.lower():
                    error_message += (
                        " Cause frequente : setting.langue invalide ou nom de voix TTS au lieu "
                        "dune locale Azure (utiliser par ex. ar-SA, pas ar-SA-HamedNeural)."
                    )
            raise RuntimeError(error_message)

        return {
            "text": "",
            "status": "unknown"
        }

    def text_to_speech(self, text: str, voice_name=None):
        if not AZURE_SPEECH_AVAILABLE:
            raise RuntimeError("La bibliothèque azure-cognitiveservices-speech n'est pas installée.")
        self._validate_azure_speech_config()

        speech_config = speechsdk.SpeechConfig(
            subscription=settings.AZURE_SPEECH_KEY,
            region=settings.AZURE_SPEECH_REGION
        )
        speech_config.speech_synthesis_voice_name = voice_name or settings.AZURE_SPEECH_VOICE

        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
        result = synthesizer.speak_text_async(text).get()

        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            return bytes(result.audio_data)

        if result.reason == speechsdk.ResultReason.Canceled:
            details = result.cancellation_details
            error_message = f"Erreur de synthèse: {details.reason}"
            if details.reason == speechsdk.CancellationReason.Error and details.error_details:
                error_message = f"{error_message} - {details.error_details}"
            raise RuntimeError(error_message)

        raise RuntimeError("La synthèse vocale n'a pas abouti.")

    @staticmethod
    def _bcp47_primary(lang: str) -> str:
        if not lang or not str(lang).strip():
            return "ar"
        return str(lang).strip().split("-")[0].lower()

    def _tts_voice_for_robot_locale(self, robot_bcp47: Optional[str], voice_name=None):
        if voice_name:
            return voice_name
        loc = (robot_bcp47 or "").strip() or settings.AZURE_SPEECH_RECOGNITION_LANGUAGE
        return resolve_tts_voice_for_bcp47_locale(loc, settings.AZURE_SPEECH_VOICE)

    @staticmethod
    def _compose_stt_with_extra_text(stt_text: str, extra_text: Optional[str]) -> str:
        """Forme « question_vocale (texte_libre) » avant traduction / n8n."""
        base = (stt_text or "").strip()
        if not extra_text or not str(extra_text).strip():
            return base
        return f"{base} ({str(extra_text).strip()})"

    def audio_to_n8n_to_audio(self, audio_bytes: bytes, voice_name=None, extra_text=None):
        safe_console_line("========== Pipeline audio -> n8n -> audio ==========")
        langue_brute = self._get_robot_langue_from_setting()
        robot_lang_setting = self._canonical_locale_for_speech_and_translation(langue_brute)
        robot_tr = self._bcp47_primary(robot_lang_setting)

        safe_console_line(
            f"Langue robot : brut (table setting) = {langue_brute!s} | normalise = {robot_lang_setting}"
        )

        stt_result = self.speech_to_text(audio_bytes)
        input_text = (stt_result or {}).get("text", "").strip()
        safe_console_line(
            f"Statut reconnaissance vocale : {stt_result.get('status') if isinstance(stt_result, dict) else 'unknown'}"
        )
        if not input_text:
            safe_console_line("Erreur : aucun texte apres conversion voix -> texte.")
            raise RuntimeError("Aucun texte reconnu depuis l'audio.")

        question_for_n8n = self._compose_stt_with_extra_text(input_text, extra_text)
        if extra_text and str(extra_text).strip():
            safe_console_line(f"Texte client a ajouter entre parentheses : {str(extra_text).strip()}")
            safe_console_line(f"Question composee (voix + texte) : {question_for_n8n}")

        if robot_tr != "fr" and not self.gemini.configured():
            raise RuntimeError(
                "GEMINI_API_KEY est requis pour traduire la langue du robot vers le français avant n8n "
                "(traduction via Google Gemini, sans Azure Translator)."
            )

        if robot_tr == "fr":
            text_fr_for_n8n = question_for_n8n
            safe_console_line(f"Traduire en francais : (deja francais, inchangé) {text_fr_for_n8n}")
        else:
            text_fr_for_n8n = self.gemini.translate_text(
                question_for_n8n, robot_lang_setting, "fr-FR"
            )
            safe_console_line(f"Traduire en francais : {text_fr_for_n8n}")

        safe_console_line("Envoi n8n (payload JSON avec le texte en francais).")
        n8n_response = self.send_to_n8n({"text": text_fr_for_n8n})

        reply_fr = self._extract_text_from_n8n_response(n8n_response)
        safe_console_line(f"Resultat brut n8n (objet ou texte brut) : {n8n_response!s}")
        safe_console_line(f"Resultat (texte extrait pour traitement, attendu francais) : {reply_fr}")
        if not reply_fr:
            safe_console_line("Erreur : n8n na pas renvoye de texte exploitable.")
            raise RuntimeError("Le workflow n8n n'a pas retourné de texte exploitable.")

        if robot_tr == "fr":
            reply_robot_lang = reply_fr
            safe_console_line(
                f"Traduction vers langue robot ({robot_lang_setting}) : (inchangé) {reply_robot_lang}"
            )
        else:
            reply_robot_lang = self.gemini.translate_text(reply_fr, "fr-FR", robot_lang_setting)
            safe_console_line(
                f"Traduction vers langue robot ({robot_lang_setting}) : {reply_robot_lang}"
            )

        chosen_voice = self._tts_voice_for_robot_locale(robot_lang_setting, voice_name)
        safe_console_line(
            f"Synthese vocale finale (langue du robot / voix Azure) voix={chosen_voice}"
        )

        output_audio = self.text_to_speech(reply_robot_lang, chosen_voice)
        safe_console_line(
            f"Audio genere : {len(output_audio)} octets (flux WAV)."
        )
        safe_console_line("========== Fin pipeline ==========")

        return {
            "robot_lang": robot_lang_setting,
            "input_text": input_text,
            "extra_text": (str(extra_text).strip() if extra_text and str(extra_text).strip() else None),
            "question_combined": question_for_n8n,
            "text_fr_for_n8n": text_fr_for_n8n,
            "reply_fr": reply_fr,
            "reply_text": reply_robot_lang,
            "audio_bytes": output_audio,
        }

    # =========================================================
    # --- GEMINI KEYWORDS ---
    # =========================================================
    def generate_robot_name_keywords(self):
        robot_name = self._get_robot_name_from_setting()
        if not robot_name:
            raise RuntimeError("Le champ 'name' de la table setting est vide ou introuvable.")

        raw_output = self.gemini.generate_keywords_from_name(robot_name)

        try:
            parsed = json.loads(raw_output)
            if not isinstance(parsed, list):
                raise RuntimeError("La réponse Gemini n'est pas une liste JSON.")
            return {
                "name": robot_name,
                "keywords": parsed
            }
        except json.JSONDecodeError:
            # Fallback si Gemini encapsule le JSON dans des balises markdown.
            cleaned = raw_output.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(cleaned)
            if not isinstance(parsed, list):
                raise RuntimeError("La réponse Gemini n'est pas une liste JSON.")
            return {
                "name": robot_name,
                "keywords": parsed
            }

    def _validate_azure_speech_config(self):
        if not settings.AZURE_SPEECH_KEY or not settings.AZURE_SPEECH_REGION:
            raise RuntimeError(
                "Configuration Azure Speech manquante. Définissez AZURE_SPEECH_KEY et AZURE_SPEECH_REGION dans le fichier .env."
            )

    def _extract_text_from_n8n_response(self, payload):
        if isinstance(payload, str):
            return payload.strip()

        if isinstance(payload, dict):
            direct_keys = ["text", "response", "answer", "message", "output", "result"]
            for key in direct_keys:
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

            # Certains workflows retournent un objet imbriqué.
            for value in payload.values():
                extracted = self._extract_text_from_n8n_response(value)
                if extracted:
                    return extracted

        if isinstance(payload, list):
            for item in payload:
                extracted = self._extract_text_from_n8n_response(item)
                if extracted:
                    return extracted

        return None

    def _get_robot_name_from_setting(self):
        res = self.client.table("setting").select("name").limit(1).execute().data
        if not res:
            return None
        return res[0].get("name")

    def _get_known_faces(self):
        now = time.time()
        if self._known_faces_cache and (now - self._known_faces_cache_at) < self._known_faces_ttl_seconds:
            return self._known_faces_cache

        # Stale-while-revalidate: ne bloque pas la requête si on a déjà un cache.
        if self._known_faces_cache:
            if not self._is_refreshing_faces:
                threading.Thread(target=self._refresh_known_faces_cache, daemon=True).start()
            return self._known_faces_cache

        # Premier chargement: on calcule immédiatement pour avoir un référentiel.
        self._refresh_known_faces_cache()
        return self._known_faces_cache

    def _invalidate_known_faces_cache(self):
        with self._cache_lock:
            self._known_faces_cache = []
            self._known_faces_cache_at = 0.0

    def _refresh_known_faces_cache(self):
        with self._cache_lock:
            if self._is_refreshing_faces:
                return
            self._is_refreshing_faces = True
        try:
            now = time.time()
            if not FACE_RECOGNITION_AVAILABLE:
                self._known_faces_cache = []
                self._known_faces_cache_at = now
                return
            try:
                rows = self.client.table("imageuser").select("idimage, iduser, url").execute().data or []
            except Exception:
                rows = []
            if not rows:
                self._known_faces_cache = []
                self._known_faces_cache_at = now
                return

            users_rows = self.client.table("utilisateur").select("iduser, nom").execute().data or []
            nom_by_user = {}
            for u in users_rows:
                uid = u.get("iduser")
                if uid is None:
                    continue
                try:
                    nom_by_user[int(uid)] = str(u.get("nom") or "inconnu")
                except (TypeError, ValueError):
                    nom_by_user[str(uid)] = str(u.get("nom") or "inconnu")

            known_faces = []
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = []
                for row in rows:
                    url = (row.get("url") or "").strip()
                    if not url:
                        continue
                    uid = row.get("iduser")
                    try:
                        uid_int = int(uid) if uid is not None else None
                    except (TypeError, ValueError):
                        uid_int = None
                    nom = "inconnu"
                    if uid_int is not None and uid_int in nom_by_user:
                        nom = nom_by_user[uid_int]
                    elif uid is not None and str(uid) in nom_by_user:
                        nom = nom_by_user[str(uid)]
                    futures.append(executor.submit(self._extract_encoding_from_url, url, nom))
                for future in as_completed(futures):
                    result = future.result()
                    if result is not None:
                        known_faces.append(result)

            self._known_faces_cache = known_faces
            self._known_faces_cache_at = now
        finally:
            with self._cache_lock:
                self._is_refreshing_faces = False

    def _extract_encoding_from_url(self, image_url: str, nom: str):
        if not image_url:
            return None
        try:
            response = httpx.get(image_url, timeout=10)
            if response.status_code != 200:
                return None
            user_image = face_recognition.load_image_file(io.BytesIO(response.content))
            user_image = self._resize_image_for_speed(user_image, max_width=800)
            user_locations = face_recognition.face_locations(user_image, model="hog")
            user_encodings = face_recognition.face_encodings(
                user_image,
                known_face_locations=user_locations,
                num_jitters=1
            )
            if not user_encodings:
                return None
            return {
                "nom": nom or "inconnu",
                "encoding": user_encodings[0]
            }
        except Exception:
            return None

    def _resize_image_for_speed(self, image, max_width=800):
        height, width = image.shape[:2]
        if width <= max_width:
            return image
        ratio = max_width / float(width)
        new_height = int(height * ratio)
        # Sous-échantillonnage rapide pour accélérer face_locations/encodings.
        step = max(1, int(width / max_width))
        resized = image[::step, ::step]
        if resized.shape[1] > max_width:
            resized = resized[:new_height, :max_width]
        return resized

    def _fix_booleans(self, data: dict) -> dict:
        new_data = data.copy()
        for k, v in new_data.items():
            if isinstance(v, bool):
                new_data[k] = 1 if v else 0
            elif isinstance(v, datetime):
                new_data[k] = v.isoformat()
        return new_data