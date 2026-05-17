from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class InformationPersonelle:
    id: int
    question: str
    reponce: str
    date: datetime
    iduser: int
    idkoda: str
    idconv: Optional[int] = None
