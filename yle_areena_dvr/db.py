import os
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone
from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.dialects.sqlite import insert
from .models import Program

DB_PATH = Path(os.path.expanduser("~/.yle-areena-dvr.db"))
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(DATABASE_URL, echo=False)

async def init_db():
    """Initializes the SQLite database and creates the necessary tables."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

async def get_program(program_id: str) -> Optional[Program]:
    """Retrieves a program from the database by its ID."""
    async with AsyncSession(engine) as session:
        return await session.get(Program, program_id)

async def save_program(program: Program, rating: Optional[float]):
    """Saves or updates a program in the database using SQLite UPSERT."""
    program.tmdb_rating = rating
    program.last_seen_at = datetime.now(timezone.utc)
    
    async with AsyncSession(engine) as session:
        # We use SQLAlchemy Core for UPSERT (ON CONFLICT DO UPDATE)
        stmt = insert(Program).values(program.model_dump())
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "title": stmt.excluded.title,
                "description": stmt.excluded.description,
                "type": stmt.excluded.type,
                "url": stmt.excluded.url,
                "tmdb_rating": stmt.excluded.tmdb_rating,
                "year": stmt.excluded.year,
                "published_at": stmt.excluded.published_at,
                "expires_at": stmt.excluded.expires_at,
                "last_seen_at": stmt.excluded.last_seen_at
            }
        )
        await session.execute(stmt)
        await session.commit()

async def mark_existing_program_seen(program_id: str):
    """Updates the last_seen_at timestamp for a program we just found on Areena."""
    async with AsyncSession(engine) as session:
        program = await session.get(Program, program_id)
        if program:
            program.last_seen_at = datetime.now(timezone.utc)
            session.add(program)
            await session.commit()

async def get_programs_missing_year(limit: int = 200) -> list[Program]:
    """Returns programs with missing year for TMDb backfill."""
    async with AsyncSession(engine) as session:
        statement = select(Program).where(Program.year.is_(None)).order_by(Program.last_seen_at.desc()).limit(limit)
        results = await session.execute(statement)
        return list(results.scalars().all())

async def search_programs_db(
    query: str, 
    limit: int = 10, 
    min_rating: Optional[float] = None,
    only_new: bool = False,
    only_expiring: bool = False
) -> list[Program]:
    """Searches the local database for programs."""
    async with AsyncSession(engine) as session:
        statement = select(Program).where(Program.title.contains(query))
        
        if min_rating is not None:
            statement = statement.where(Program.tmdb_rating >= min_rating)
            
        if only_new:
            statement = statement.where(Program.published_at.is_not(None))
            statement = statement.order_by(Program.published_at.desc())
        elif only_expiring:
            statement = statement.where(Program.expires_at.is_not(None))
            statement = statement.order_by(Program.expires_at.asc())
        else:
            # Default order by last seen or added
            statement = statement.order_by(Program.last_seen_at.desc())
            
        statement = statement.limit(limit)
        results = await session.execute(statement)
        return list(results.scalars().all())
