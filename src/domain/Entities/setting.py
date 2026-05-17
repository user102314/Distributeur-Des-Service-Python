from dataclasses import dataclass


@dataclass
class Setting:
    """Table setting — clé primaire idkoda."""

    idkoda: str
    name: str
    sexe: str
    date: str
    motdepasse: str
    etat: bool
    caractere: str
    langue: str = ""
