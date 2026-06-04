from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ---- NOTE / ACTIVITÉS (table note) ----
class ActivityCreate(BaseModel):
    note: str
    etat: bool = False
    date: Optional[datetime] = None
    idkoda: str = ""


class ActivityUpdate(BaseModel):
    note: Optional[str] = None
    etat: Optional[bool] = None
    date: Optional[datetime] = None
    idkoda: Optional[str] = None


class NoteCreate(BaseModel):
    note: str
    etat: bool = False
    date: Optional[datetime] = None
    idkoda: str = ""


class NoteUpdate(BaseModel):
    note: Optional[str] = None
    etat: Optional[bool] = None
    date: Optional[datetime] = None
    idkoda: Optional[str] = None


# ---- SETTING ----
class SettingUpdate(BaseModel):
    name: Optional[str] = None
    sexe: Optional[str] = None
    date: Optional[str] = None
    motdepasse: Optional[str] = None
    etat: Optional[bool] = None
    caractere: Optional[str] = None
    langue: Optional[str] = None


# ---- AUDIO ----
class TextToSpeechRequest(BaseModel):
    text: str
    voice_name: Optional[str] = None


# ---- UTILISATEUR ----
class UtilisateurCreate(BaseModel):
    nom: str
    idkoda: str = ""


class UtilisateurUpdate(BaseModel):
    nom: Optional[str] = None
    idkoda: Optional[str] = None


# ---- IMAGE UTILISATEUR ----
class ImageUserCreate(BaseModel):
    iduser: int
    url: str


class ImageUserUpdate(BaseModel):
    iduser: Optional[int] = None
    url: Optional[str] = None


# ---- ACCOMPAGNEMENT ----
class AccompagnementCreate(BaseModel):
    interets: str = ""
    synthese: str = ""
    point_cles: str = ""
    conseils: str = ""
    iduser: int


class AccompagnementUpdate(BaseModel):
    interets: Optional[str] = None
    synthese: Optional[str] = None
    point_cles: Optional[str] = None
    conseils: Optional[str] = None
    iduser: Optional[int] = None


# ---- CONVERSATION ----
class ConversationCreate(BaseModel):
    question: str
    reponce: str = ""
    typedequestion: str = ""
    iduser: int
    idkoda: str = ""
    date: Optional[datetime] = None


class ConversationUpdate(BaseModel):
    question: Optional[str] = None
    reponce: Optional[str] = None
    typedequestion: Optional[str] = None
    iduser: Optional[int] = None
    idkoda: Optional[str] = None
    date: Optional[datetime] = None


# ---- HISTORIQUE ----
class HistoriqueCreate(BaseModel):
    question: str
    reponce: str = ""
    type_question: str = ""
    idkoda: str = ""


# ---- INFORMATION PERSONNELLE ----
class InformationPersonelleCreate(BaseModel):
    question: str
    reponce: str = ""
    iduser: int
    idkoda: str = ""
    idconv: Optional[int] = None
    date: Optional[datetime] = None


class InformationPersonelleUpdate(BaseModel):
    question: Optional[str] = None
    reponce: Optional[str] = None
    iduser: Optional[int] = None
    idkoda: Optional[str] = None
    idconv: Optional[int] = None
    date: Optional[datetime] = None


# ---- AUTHENTIFICATION ----
class AuthentificationCreate(BaseModel):
    idproduit: int = Field(..., description="Identifiant produit (clé métier)")
    emailclient: str
    motdepasse: str
    idkoda: str = ""


class AuthentificationUpdate(BaseModel):
    emailclient: Optional[str] = None
    motdepasse: Optional[str] = None
    idkoda: Optional[str] = None


class LoginRequest(BaseModel):
    emailclient: str
    motdepasse: str


class NomWebhookRequest(BaseModel):
    """Corps pour POST /api/webhook/nom — déclenche le workflow n8n par nom."""

    nom: str = Field(..., min_length=1, description="Nom envoyé au webhook n8n")
