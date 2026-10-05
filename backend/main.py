from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from sqlalchemy import text

load_dotenv()

from database import engine, get_db, Base
import models


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

# Enable pgvector extension
with engine.connect() as conn:
    conn.execute(
        text("CREATE EXTENSION IF NOT EXISTS vector")
    )
    conn.commit()


# Create tables that do not already exist.
#
# This includes:
#
#   users
#   claims
#   evidences
#   complaints
#   gem_transactions
#   fact_checker_badges
#
Base.metadata.create_all(bind=engine)


# ============================================================
# EXISTING DATABASE FIXES
# ============================================================

with engine.begin() as conn:

    # Complaint workflow column
    conn.execute(
        text(
            """
            ALTER TABLE complaints
            ADD COLUMN IF NOT EXISTS recipient_email VARCHAR
            """
        )
    )

    # Complaint lookup index
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS
            idx_complaints_claim_source_sent
            ON complaints (claim_id, source_url, is_sent)
            """
        )
    )


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="NewsCloud Verification API"
)


# ============================================================
# ROUTERS
# ============================================================

from routers import (
    auth,
    claims,
    complaints,
    badges,
    leaderboard,
)

app.include_router(auth.router)
app.include_router(claims.router)
app.include_router(complaints.router)
app.include_router(badges.router)
app.include_router(leaderboard.router)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def read_root():
    return {
        "message": "Welcome to NewsCloud Verification API"
    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health_check(
    db: Session = Depends(get_db)
):
    return {
        "status": "healthy",
        "database": "connected"
    }