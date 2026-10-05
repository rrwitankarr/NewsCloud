from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

import auth
import models
from database import get_db


router = APIRouter(
    prefix="/api/badges",
    tags=["badges"]
)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_previous_month(year: int, month: int):
    """
    Return (year, month) for the previous calendar month.
    """

    if month == 1:
        return year - 1, 12

    return year, month - 1


def get_month_boundaries(year: int, month: int):
    """
    Return the UTC start and end boundaries for a calendar month.

    Example:

        September 2026

        start = 2026-09-01 00:00:00 UTC
        end   = 2026-10-01 00:00:00 UTC
    """

    start = datetime(
        year,
        month,
        1,
        tzinfo=timezone.utc
    )

    if month == 12:
        end = datetime(
            year + 1,
            1,
            1,
            tzinfo=timezone.utc
        )
    else:
        end = datetime(
            year,
            month + 1,
            1,
            tzinfo=timezone.utc
        )

    return start, end


def get_badge_number(
    db: Session,
    user_id: int
) -> int:
    """
    Determine the next badge number for a user.

    First win  -> 1
    Second win -> 2
    Third win  -> 3
    """

    count = (
        db.query(models.FactCheckerBadge)
        .filter(
            models.FactCheckerBadge.user_id == user_id
        )
        .count()
    )

    return count + 1


# ============================================================
# FINALIZE PREVIOUS MONTH'S WINNER
# ============================================================

def finalize_previous_month_winner(
    db: Session,
    current_year: int,
    current_month: int
):
    """
    Determine the user who earned the most GEMs during the
    previous calendar month.

    IMPORTANT:
    This does NOT use User.gem_score.

    Instead, it calculates:

        SUM(GemTransaction.amount)

    for each user during the previous month.

    A badge is created only once for that month.
    """

    previous_year, previous_month = get_previous_month(
        current_year,
        current_month
    )

    # --------------------------------------------------------
    # Check whether a badge has already been created
    # for this month.
    #
    # Since there is only one winner, if any badge exists
    # for the month/year, the month has already been finalized.
    # --------------------------------------------------------

    existing_badge = (
        db.query(models.FactCheckerBadge)
        .filter(
            models.FactCheckerBadge.award_year == previous_year,
            models.FactCheckerBadge.award_month == previous_month
        )
        .first()
    )

    if existing_badge:
        return existing_badge

    # --------------------------------------------------------
    # Get previous month's time boundaries
    # --------------------------------------------------------

    month_start, month_end = get_month_boundaries(
        previous_year,
        previous_month
    )

    # --------------------------------------------------------
    # Find the user who earned the most GEMs during
    # the previous month.
    #
    # We deliberately DO NOT use:
    #
    #     User.gem_score
    #
    # because that represents the user's accumulated
    # GEM balance.
    #
    # Instead:
    #
    #     SUM(GemTransaction.amount)
    #
    # gives us only the GEMs earned during this month.
    #
    # Tie breaker:
    # If two users earned the same number of GEMs,
    # the user with the lower user ID is selected.
    # This preserves the deterministic tie-breaking behavior
    # of the previous implementation.
    # --------------------------------------------------------

    winner_data = (
        db.query(
            models.GemTransaction.user_id,
            func.sum(
                models.GemTransaction.amount
            ).label("monthly_gems")
        )
        .filter(
            models.GemTransaction.created_at >= month_start,
            models.GemTransaction.created_at < month_end
        )
        .group_by(
            models.GemTransaction.user_id
        )
        .order_by(
            func.sum(
                models.GemTransaction.amount
            ).desc(),
            models.GemTransaction.user_id.asc()
        )
        .first()
    )

    # --------------------------------------------------------
    # No GEM transactions during the previous month.
    #
    # Therefore there is no Top Fact Checker for that month.
    # --------------------------------------------------------

    if not winner_data:
        return None

    winner_id = winner_data.user_id
    monthly_gems = int(winner_data.monthly_gems)

    # --------------------------------------------------------
    # Make sure the winning user still exists.
    # --------------------------------------------------------

    winner = (
        db.query(models.User)
        .filter(
            models.User.id == winner_id
        )
        .first()
    )

    if not winner:
        return None

    # --------------------------------------------------------
    # Determine badge number for winner
    # --------------------------------------------------------

    badge_number = get_badge_number(
        db,
        winner.id
    )

    # --------------------------------------------------------
    # Create badge
    # --------------------------------------------------------

    badge = models.FactCheckerBadge(
        user_id=winner.id,

        award_month=previous_month,

        award_year=previous_year,

        # IMPORTANT:
        # This is the number of GEMs earned during the
        # winning month, NOT the user's lifetime gem_score.
        gems_at_award=monthly_gems,

        badge_number=badge_number,

        title="Top Fact Checker"
    )

    db.add(badge)

    db.commit()

    db.refresh(badge)

    return badge


# ============================================================
# GET CURRENT USER'S BADGES
# ============================================================

@router.get("/mine")
def get_my_badges(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.get_current_user
    ),
):
    """
    Return all Fact Checker badges belonging to
    the currently logged-in user.
    """

    badges = (
        db.query(models.FactCheckerBadge)
        .filter(
            models.FactCheckerBadge.user_id == current_user.id
        )
        .order_by(
            models.FactCheckerBadge.award_year.desc(),
            models.FactCheckerBadge.award_month.desc()
        )
        .all()
    )

    return {
        "badge_count": len(badges),

        "badges": [
            {
                "badge_number": badge.badge_number,

                "award_month": badge.award_month,

                "award_year": badge.award_year,

                "title": badge.title,
            }
            for badge in badges
        ]
    }


# ============================================================
# GET CURRENT MONTH'S FEATURED FACT CHECKER
# ============================================================

@router.get("/featured")
def get_featured_fact_checker(
    db: Session = Depends(get_db),
):
    """
    During the first 7 days of a month:

        Display the previous month's winner.

    From day 8 onward:

        Hide the featured winner.

    Example:

        October 1-7
        -> September winner displayed

        October 8-31
        -> Nothing displayed
    """

    now = datetime.now(timezone.utc)

    current_year = now.year
    current_month = now.month

    # --------------------------------------------------------
    # Only display during days 1-7
    # --------------------------------------------------------

    if now.day > 7:
        return {
            "display": False
        }

    # --------------------------------------------------------
    # Finalize previous month's winner
    # --------------------------------------------------------

    badge = finalize_previous_month_winner(
        db,
        current_year,
        current_month
    )

    if not badge:
        return {
            "display": False
        }

    # --------------------------------------------------------
    # Get winning user
    # --------------------------------------------------------

    winner = (
        db.query(models.User)
        .filter(
            models.User.id == badge.user_id
        )
        .first()
    )

    if not winner:
        return {
            "display": False
        }

    # --------------------------------------------------------
    # Month name
    # --------------------------------------------------------

    month_name = datetime(
        badge.award_year,
        badge.award_month,
        1
    ).strftime("%B")

    # --------------------------------------------------------
    # Return featured winner
    # --------------------------------------------------------

    return {
        "display": True,

        "title": "Top Fact Checker",

        "username": winner.username,

        # Monthly GEMs earned by the winner
        "gems": badge.gems_at_award,

        "month": month_name,

        "year": badge.award_year
    }