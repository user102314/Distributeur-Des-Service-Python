from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse
from src.application.app_service_impl import ApiServiceImpl
from src.controllers.schemas import (
    AccompagnementCreate,
    AccompagnementUpdate,
    ActivityCreate,
    ActivityUpdate,
    AuthentificationCreate,
    AuthentificationUpdate,
    ConversationCreate,
    ConversationUpdate,
    HistoriqueCreate,
    InformationPersonelleCreate,
    InformationPersonelleUpdate,
    ImageUserCreate,
    ImageUserUpdate,
    LoginRequest,
    NomWebhookRequest,
    NoteCreate,
    NoteUpdate,
    SettingUpdate,
    TextToSpeechRequest,
    UtilisateurCreate,
    UtilisateurUpdate,
)

router = APIRouter()
service = ApiServiceImpl()


@router.get("/db-test", summary="Test de connexion à Supabase")
def db_test():
    """Lit une ligne sur la table setting pour vérifier que la base répond."""
    from src.infrastructure.database import get_supabase_client

    try:
        client = get_supabase_client()
        res = client.table("setting").select("*").limit(1).execute()
        rows = res.data or []
        return {
            "status": "ok",
            "database": "connected",
            "table": "setting",
            "rows_sampled": len(rows),
        }
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Connexion base de données échouée: {exc}",
        ) from exc


# ==============================================================
# ENDPOINTS UTILISATEURS
# ==============================================================
@router.get("/users", summary="Lister tous les utilisateurs")
def get_users():
    return service.get_all_users()


@router.get("/users/{iduser}", summary="Obtenir un utilisateur par iduser")
def get_user(iduser: int):
    row = service.get_user(iduser)
    if not row:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return row


@router.post("/users", summary="Créer un utilisateur", status_code=201)
def create_user(data: UtilisateurCreate):
    return service.create_user(data.model_dump(exclude_none=True))


@router.put("/users/{iduser}", summary="Mettre à jour un utilisateur")
def update_user(iduser: int, data: UtilisateurUpdate):
    payload = data.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=400, detail="Aucun champ à mettre à jour")
    return service.update_user(iduser, payload)


@router.delete("/users/{iduser}", summary="Supprimer un utilisateur")
def delete_user(iduser: int):
    return service.delete_user(iduser)

# ==============================================================
# ENDPOINTS IMAGES UTILISATEUR (table imageuser)
# ==============================================================
@router.get("/user-images", summary="Lister les images utilisateur")
def list_user_images():
    return service.get_all_user_images()


@router.get("/user-images/{idimage}", summary="Obtenir une ligne imageuser")
def get_user_image_row(idimage: int):
    row = service.get_user_image(idimage)
    if not row:
        raise HTTPException(status_code=404, detail="Image utilisateur introuvable")
    return row


@router.get("/user-images/by-user/{iduser}", summary="Images pour un iduser")
def get_user_images_for_user(iduser: int):
    return service.get_user_images_by_user(iduser)


@router.post("/user-images", summary="Enregistrer une image utilisateur (url)", status_code=201)
def create_user_image(data: ImageUserCreate):
    return service.create_user_image(data.model_dump(exclude_none=True))


@router.put("/user-images/{idimage}", summary="Mettre à jour une image utilisateur")
def update_user_image_row(idimage: int, data: ImageUserUpdate):
    payload = data.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=400, detail="Aucun champ à mettre à jour")
    return service.update_user_image(idimage, payload)


@router.delete("/user-images/{idimage}", summary="Supprimer une image utilisateur")
def delete_user_image_row(idimage: int):
    return service.delete_user_image(idimage)

# ==============================================================
# ENDPOINTS HISTORIQUE
# ==============================================================
@router.get("/history", summary="Lister tout l'historique")
def get_history():
    return service.get_all_history()


@router.get("/history/{historique_id}", summary="Obtenir une entrée d'historique")
def get_historique(historique_id: int):
    row = service.get_historique(historique_id)
    if not row:
        raise HTTPException(status_code=404, detail="Historique introuvable")
    return row


@router.post("/history", summary="Ajouter une entrée d'historique", status_code=201)
def create_historique(data: HistoriqueCreate):
    return service.create_historique(data.model_dump(exclude_none=True))


@router.delete("/history/{historique_id}", summary="Supprimer une entrée d'historique")
def delete_historique(historique_id: int):
    return service.delete_historique(historique_id)

# ==============================================================
# ENDPOINTS CONVERSATIONS
# ==============================================================
@router.get("/conversations/last100", summary="100 dernières conversations")
def get_convs():
    return service.get_last_100_conversations()


@router.get("/conversations", summary="Lister toutes les conversations")
def list_conversations(
    date_from: str | None = Query(None, description="Date début (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="Date fin (YYYY-MM-DD)"),
):
    from datetime import datetime as dt

    try:
        df = dt.fromisoformat(date_from) if date_from else None
        dte = dt.fromisoformat(date_to) if date_to else None
        return service.get_all_conversations(date_from=df, date_to=dte)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Base de données indisponible: {exc}") from exc


@router.get("/conversations/{idconv}", summary="Obtenir une conversation")
def get_conversation(idconv: int):
    row = service.get_conversation(idconv)
    if not row:
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    return row


@router.post("/conversations", summary="Créer une conversation", status_code=201)
def create_conversation(data: ConversationCreate):
    return service.create_conversation(data.model_dump(exclude_none=True))


@router.put("/conversations/{idconv}", summary="Mettre à jour une conversation")
def update_conversation(idconv: int, data: ConversationUpdate):
    payload = data.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=400, detail="Aucune donnée fournie")
    return service.update_conversation(idconv, payload)


@router.delete("/conversations/{idconv}", summary="Supprimer une conversation")
def delete_conversation(idconv: int):
    return service.delete_conversation(idconv)

# ==============================================================
# ENDPOINTS NOTES
# ==============================================================
@router.get("/notes", summary="Lister toutes les notes")
def get_notes():
    return service.get_all_notes()


@router.get("/notes/{note_id}", summary="Obtenir une note")
def get_note(note_id: int):
    row = service.get_note(note_id)
    if not row:
        raise HTTPException(status_code=404, detail="Note introuvable")
    return row


@router.post("/notes", summary="Créer une note", status_code=201)
def create_note(data: NoteCreate):
    return service.create_note(data.model_dump(exclude_none=True))


@router.put("/notes/{note_id}", summary="Mettre à jour une note")
def update_note_full(note_id: int, data: NoteUpdate):
    payload = data.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=400, detail="Aucune donnée fournie")
    return service.update_note(note_id, payload)


@router.delete("/notes/{note_id}", summary="Supprimer une note")
def delete_note(note_id: int):
    return service.delete_note(note_id)


@router.patch("/notes/{note_id}/etat", summary="Modifier l'état d'une note")
def update_note_etat(note_id: int, etat: bool):
    return service.modify_note_etat(note_id, etat)

# ==============================================================
# ENDPOINTS SETTINGS
# ==============================================================
@router.get("/settings", summary="Obtenir les paramètres")
def get_settings():
    return service.get_settings()

@router.put("/settings", summary="Modifier les paramètres")
def update_settings(data: SettingUpdate):
    payload = data.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=400, detail="Aucun champ à mettre à jour")
    return service.modify_settings(payload)

# ==============================================================
# ENDPOINTS INFORMATIONS PERSONNELLES
# ==============================================================
@router.get("/personal-info", summary="Obtenir les informations personnelles")
def get_all_info():
    return service.get_personal_info()


@router.get("/personal-info/user/{iduser}", summary="Infos personnelles pour un utilisateur")
def get_personal_info_by_user(iduser: int):
    return service.get_personal_info_by_user(iduser)


@router.post("/personal-info", summary="Ajouter des informations personnelles", status_code=201)
def save_info(data: InformationPersonelleCreate):
    return service.add_personal_info(data.model_dump(exclude_none=True))


@router.put("/personal-info/{info_id}", summary="Mettre à jour une information personnelle")
def update_personal_info(info_id: int, data: InformationPersonelleUpdate):
    payload = data.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=400, detail="Aucune donnée fournie")
    return service.update_personal_info(info_id, payload)


@router.delete("/personal-info/{info_id}", summary="Supprimer une information personnelle")
def delete_personal_info(info_id: int):
    return service.delete_personal_info(info_id)


# ==============================================================
# ENDPOINTS ACCOMPAGNEMENT
# ==============================================================
@router.get("/accompagnements", summary="Lister tous les accompagnements")
def list_accompagnements():
    return service.get_all_accompagnements()


@router.get("/accompagnements/user/{iduser}", summary="Accompagnements par utilisateur")
def list_accompagnements_by_user(iduser: int):
    return service.get_accompagnements_by_user(iduser)


@router.get("/accompagnements/{accompagnement_id}", summary="Obtenir un accompagnement")
def get_accompagnement(accompagnement_id: int):
    row = service.get_accompagnement(accompagnement_id)
    if not row:
        raise HTTPException(status_code=404, detail="Accompagnement introuvable")
    return row


@router.post("/accompagnements", summary="Créer un accompagnement", status_code=201)
def create_accompagnement(data: AccompagnementCreate):
    return service.create_accompagnement(data.model_dump(exclude_none=True))


@router.put("/accompagnements/{accompagnement_id}", summary="Mettre à jour un accompagnement")
def update_accompagnement(accompagnement_id: int, data: AccompagnementUpdate):
    payload = data.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=400, detail="Aucune donnée fournie")
    return service.update_accompagnement(accompagnement_id, payload)


@router.delete("/accompagnements/{accompagnement_id}", summary="Supprimer un accompagnement")
def delete_accompagnement(accompagnement_id: int):
    return service.delete_accompagnement(accompagnement_id)


# ==============================================================
# ENDPOINTS AUTHENTIFICATION
# ==============================================================
@router.post("/auth/login", summary="Connexion client (email + mot de passe)")
def auth_login(data: LoginRequest):
    try:
        result = service.login(data.emailclient.strip(), data.motdepasse)
    except Exception as exc:
        exc_name = type(exc).__name__
        if "Timeout" in exc_name or "Connect" in exc_name:
            raise HTTPException(
                status_code=503,
                detail="Base de données Supabase injoignable (timeout réseau). Réessayez dans quelques secondes.",
            ) from exc
        raise
    if not result:
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    return {"status": "ok", "data": result}


@router.get("/auth/registrations", summary="Lister les enregistrements authentification")
def list_auth():
    return service.list_authentifications()


@router.get("/auth/registrations/{idproduit}", summary="Obtenir une ligne authentification par idproduit")
def get_auth(idproduit: int):
    row = service.get_authentification(idproduit)
    if not row:
        raise HTTPException(status_code=404, detail="Authentification introuvable")
    return row


@router.post("/auth/registrations", summary="Créer une authentification", status_code=201)
def create_auth(data: AuthentificationCreate):
    return service.create_authentification(data.model_dump(exclude_none=True))


@router.put("/auth/registrations/{idproduit}", summary="Mettre à jour une authentification")
def update_auth(idproduit: int, data: AuthentificationUpdate):
    payload = data.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=400, detail="Aucune donnée fournie")
    return service.update_authentification(idproduit, payload)


@router.delete("/auth/registrations/{idproduit}", summary="Supprimer une authentification")
def delete_auth(idproduit: int):
    return service.delete_authentification(idproduit)


# ==============================================================
# ENDPOINT N8N
# ==============================================================
@router.post("/trigger-n8n", summary="Déclencher un workflow n8n")
def trigger_n8n_workflow(payload: dict):
    """Envoie n'importe quelle donnée à n8n (ex: une question pour traitement IA)"""
    return service.send_to_n8n(payload)


@router.post("/webhook/nom", summary="Envoyer un nom au webhook n8n dédié")
def trigger_nom_webhook(data: NomWebhookRequest):
    """
    Reçoit un **nom**, l'envoie au webhook n8n configuré
    (``N8N_NOM_WEBHOOK_URL``, défaut : localhost:5678/webhook/7f1955c0-...)
    et retourne la réponse du workflow.
    """
    result = service.send_nom_to_webhook(data.nom)
    if isinstance(result, dict) and result.get("status") == "error":
        raise HTTPException(status_code=502, detail=result.get("message", "Erreur webhook n8n"))
    return {"status": "ok", "nom": data.nom.strip(), "data": result}

# ==============================================================
# ENDPOINTS ACTIVITY (alias table note, rétrocompatibilité)
# ==============================================================
@router.get("/activities", summary="Lister toutes les activités")
def get_activities():
    return service.get_all_activities()

@router.get("/activities/{activity_id}", summary="Obtenir une activité par ID")
def get_activity(activity_id: int):
    result = service.get_activity(activity_id)
    if not result:
        raise HTTPException(status_code=404, detail="Activité introuvable")
    return result

@router.post("/activities", summary="Créer une activité", status_code=201)
def create_activity(data: ActivityCreate):
    return service.create_activity(data.model_dump(exclude_none=True))

@router.put("/activities/{activity_id}", summary="Mettre à jour une activité")
def update_activity(activity_id: int, data: ActivityUpdate):
    payload = data.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=400, detail="Aucune donnée fournie")
    return service.update_activity(activity_id, payload)

@router.delete("/activities/{activity_id}", summary="Supprimer une activité")
def delete_activity(activity_id: int):
    return service.delete_activity(activity_id)

# ==============================================================
# ENDPOINT RECONNAISSANCE FACIALE
# ==============================================================
@router.post("/identify-face", summary="Identifier une personne par reconnaissance faciale")
async def identify_face(file: UploadFile = File(...)):
    """
    Compare la photo aux enregistrements de la table <b>imageuser</b> (URL),
    résout le <b>nom</b> via <b>utilisateur.iduser</b>, ou retourne <code>inconnu</code>.
    """
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Le fichier doit être une image")
    image_bytes = await file.read()
    try:
        name = service.identify_face(image_bytes)
        return {"nom": name}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la reconnaissance: {str(e)}")

# ==============================================================
# ENDPOINTS POWER ON / OFF
# ==============================================================
@router.post("/power-off", summary="Éteindre le système (etat = 0)")
def power_off():
    """
    Met le champ 'etat' dans la table setting à 0 (False).
    Signifie que le robot/distributeur est éteint.
    """
    return service.power_off()

@router.post("/power-on", summary="Allumer le système (etat = 1)")
def power_on():
    """
    Met le champ 'etat' dans la table setting à 1 (True).
    Signifie que le robot/distributeur est allumé.
    """
    return service.power_on()


# ==============================================================
# ENDPOINTS AUDIO (AZURE SPEECH)
# ==============================================================
@router.post("/audio/speech-to-text", summary="Convertir un fichier audio en texte")
async def speech_to_text(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Le fichier doit être un audio")

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Le fichier audio est vide")

    try:
        return service.speech_to_text(audio_bytes)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur Speech-to-Text: {str(e)}")


@router.post("/audio/text-to-speech", summary="Convertir du texte en audio")
def text_to_speech(payload: TextToSpeechRequest):
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Le texte ne doit pas être vide")

    try:
        audio_data = service.text_to_speech(payload.text, payload.voice_name)
        return StreamingResponse(
            iter([audio_data]),
            media_type="audio/wav",
            headers={"Content-Disposition": "inline; filename=tts.wav"}
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur Text-to-Speech: {str(e)}")


@router.post("/audio/speech-to-n8n-to-speech", summary="Audio -> texte -> n8n -> audio")
async def speech_to_n8n_to_speech(
    file: UploadFile = File(...),
    voice_name: str = Form(None),
    extra_text: str = Form(
        None,
        description="Texte ajouté entre parenthèses après la question STT, ex. « bonjour (oussema) »",
    ),
):
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Le fichier doit être un audio")

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Le fichier audio est vide")

    try:
        result = service.audio_to_n8n_to_audio(audio_bytes, voice_name, extra_text)
        return StreamingResponse(
            iter([result["audio_bytes"]]),
            media_type="audio/wav",
            headers={"Content-Disposition": "inline; filename=n8n_reply.wav"}
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        try:
            detail = f"Erreur pipeline audio n8n: {e!s}"
        except Exception:
            detail = "Erreur pipeline audio n8n."
        raise HTTPException(status_code=500, detail=detail)


# ==============================================================
# ENDPOINT GEMINI KEYWORDS (ROBOT NAME)
# ==============================================================
@router.get("/keywords/robot-name", summary="Générer les variantes du nom du robot via Gemini")
def get_robot_name_keywords():
    try:
        return service.generate_robot_name_keywords()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur Gemini keywords: {str(e)}")