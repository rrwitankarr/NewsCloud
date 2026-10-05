from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    Float,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

from database import Base


# ============================================================
# USER
# ============================================================

class User(Base):
    __tablename__ = "users"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    username = Column(
        String,
        unique=True,
        index=True,
        nullable=False
    )

    email = Column(
        String,
        unique=True,
        index=True,
        nullable=False
    )

    hashed_password = Column(
        String,
        nullable=False
    )

    # Lifetime GEM balance
    gem_score = Column(
        Integer,
        default=0
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    # --------------------------------------------------------
    # Existing relationships
    # --------------------------------------------------------

    complaints = relationship(
        "Complaint",
        back_populates="user"
    )

    # --------------------------------------------------------
    # GEM transactions
    # --------------------------------------------------------

    gem_transactions = relationship(
        "GemTransaction",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="GemTransaction.created_at.desc()"
    )

    # --------------------------------------------------------
    # Fact Checker badges
    # --------------------------------------------------------

    fact_checker_badges = relationship(
        "FactCheckerBadge",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="FactCheckerBadge.award_year.desc(), "
                 "FactCheckerBadge.award_month.desc()"
    )


# ============================================================
# GEM TRANSACTION
# ============================================================

class GemTransaction(Base):
    __tablename__ = "gem_transactions"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    # --------------------------------------------------------
    # User receiving the GEMs
    # --------------------------------------------------------

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    # --------------------------------------------------------
    # Number of GEMs awarded
    #
    # NewsCloud currently awards +1 GEM for a successfully
    # sent misinformation complaint.
    # --------------------------------------------------------

    amount = Column(
        Integer,
        nullable=False
    )

    # --------------------------------------------------------
    # Reason for the GEM transaction
    # --------------------------------------------------------

    reason = Column(
        String,
        nullable=False
    )

    # --------------------------------------------------------
    # When the GEMs were awarded
    #
    # This timestamp determines which month the GEMs
    # belong to.
    # --------------------------------------------------------

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True
    )

    # --------------------------------------------------------
    # Relationship
    # --------------------------------------------------------

    user = relationship(
        "User",
        back_populates="gem_transactions"
    )


# ============================================================
# CLAIM
# ============================================================

class Claim(Base):
    __tablename__ = "claims"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    content = Column(
        Text,
        nullable=False
    )

    embedding = Column(
        Vector(384)
    )

    verdict = Column(
        String
    )

    explanation = Column(
        Text
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    evidences = relationship(
        "Evidence",
        back_populates="claim"
    )


# ============================================================
# EVIDENCE
# ============================================================

class Evidence(Base):
    __tablename__ = "evidences"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    claim_id = Column(
        Integer,
        ForeignKey("claims.id")
    )

    source_url = Column(
        String
    )

    chunk_text = Column(
        Text
    )

    similarity_score = Column(
        Float
    )

    claim = relationship(
        "Claim",
        back_populates="evidences"
    )


# ============================================================
# COMPLAINT
# ============================================================

class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id")
    )

    claim_id = Column(
        Integer,
        ForeignKey("claims.id")
    )

    source_url = Column(
        String,
        nullable=False
    )

    recipient_email = Column(
        String,
        nullable=True
    )

    draft_text = Column(
        Text
    )

    is_sent = Column(
        Boolean,
        default=False
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    user = relationship(
        "User",
        back_populates="complaints"
    )

    claim = relationship(
        "Claim"
    )


# ============================================================
# FACT CHECKER BADGE
# ============================================================

class FactCheckerBadge(Base):
    __tablename__ = "fact_checker_badges"

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Only ONE Top Fact Checker badge can exist for a
    # particular month and year.
    #
    # Example:
    #
    # September 2026 -> one badge
    # October 2026   -> one badge
    # November 2026  -> one badge
    # --------------------------------------------------------

    __table_args__ = (
        UniqueConstraint(
            "award_year",
            "award_month",
            name="uq_fact_checker_badge_month"
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    # --------------------------------------------------------
    # User who earned the badge
    # --------------------------------------------------------

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    # --------------------------------------------------------
    # Month in which the user was the Top Fact Checker
    # --------------------------------------------------------

    award_month = Column(
        Integer,
        nullable=False
    )

    # --------------------------------------------------------
    # Year in which the user was the Top Fact Checker
    # --------------------------------------------------------

    award_year = Column(
        Integer,
        nullable=False
    )

    # --------------------------------------------------------
    # Total GEMs earned during that particular month
    #
    # IMPORTANT:
    # This is NOT the user's lifetime gem_score.
    #
    # It is the sum of the user's GemTransaction.amount
    # values during the winning month.
    # --------------------------------------------------------

    gems_at_award = Column(
        Integer,
        nullable=False
    )

    # --------------------------------------------------------
    # Badge sequence for that user
    #
    # First win  -> 1
    # Second win -> 2
    # Third win  -> 3
    # --------------------------------------------------------

    badge_number = Column(
        Integer,
        nullable=False
    )

    # --------------------------------------------------------
    # Badge title
    # --------------------------------------------------------

    title = Column(
        String,
        nullable=False,
        default="Top Fact Checker"
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    # --------------------------------------------------------
    # Relationship
    # --------------------------------------------------------

    user = relationship(
        "User",
        back_populates="fact_checker_badges"
    )