from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Conversation:
    idconv: int
    question: str
    reponce: str
    date: datetime
    typedequestion: str
    iduser: int
    idkoda: str
