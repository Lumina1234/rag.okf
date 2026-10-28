"""Telegram conversation state tracking."""

from enum import IntEnum


class ConversationState(IntEnum):
    IDLE = 0
    WAITING_SUBJECT_SELECT = 1
    WAITING_PDF_UPLOAD = 2
    WAITING_QUESTION = 3
    WAITING_SUMMARY_SUBJECT = 4
    WAITING_PYQ_SUBJECT = 5
    WAITING_QUIZ_SUBJECT = 6
    WAITING_SUMMARY_INPUT = 7
    WAITING_EMAIL = 8
    WAITING_IMP_QUESTIONS = 9
    WAITING_QUIZ_INPUT = 10
    WAITING_PYQ_INPUT = 11


user_sessions: dict[int, dict] = {}


def get_session(telegram_id: int) -> dict:
    if telegram_id not in user_sessions:
        user_sessions[telegram_id] = {
            "subject_id": None,
            "mode": "qa",
            "state": ConversationState.IDLE,
        }
    return user_sessions[telegram_id]


def set_session(telegram_id: int, **kwargs) -> None:
    session = get_session(telegram_id)
    session.update(kwargs)


def clear_session(telegram_id: int) -> None:
    user_sessions.pop(telegram_id, None)
