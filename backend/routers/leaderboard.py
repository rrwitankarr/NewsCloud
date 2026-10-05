from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import models
from database import get_db


router = APIRouter(
    prefix="/api/leaderboard",
    tags=["leaderboard"],
)


@router.get("")
def get_leaderboard(
    db: Session = Depends(get_db),
):
    """
    Return users ordered by their lifetime GEM balance.

    The GEM balance is stored in users.gem_score.

    Higher GEM score = higher position.
    """

    users = (
        db.query(models.User)
        .order_by(
            models.User.gem_score.desc(),
            models.User.id.asc(),
        )
        .all()
    )

    leaderboard = []

    for rank, user in enumerate(users, start=1):
        leaderboard.append(
            {
                "rank": rank,
                "username": user.username,
                "gems": user.gem_score or 0,
            }
        )

    return {
        "leaderboard": leaderboard
    }