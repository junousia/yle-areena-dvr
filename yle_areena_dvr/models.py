from pydantic import BaseModel, Field as PydanticField
from sqlmodel import SQLModel, Field
from datetime import datetime, timezone

class YleImage(BaseModel):
    id: str

class YleTitle(BaseModel):
    fi: str | None = None
    sv: str | None = None
    en: str | None = None

class YleProgram(BaseModel):
    id: str
    title: YleTitle
    type: str
    publication_event: list[dict] = PydanticField(alias="publicationEvent", default_factory=list)
    image: YleImage | None = None

class Program(SQLModel, table=True):
    __tablename__ = "movies"
    
    id: str = Field(primary_key=True)
    title: str
    description: str | None = None
    type: str = Field(default="program")
    url: str
    tmdb_rating: float | None = None
    year: int | None = None
    published_at: datetime | None = None
    expires_at: datetime | None = None
    added_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
