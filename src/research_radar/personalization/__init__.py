"""Feedback-informed reranking and visibility controls."""

from __future__ import annotations

from research_radar.models import PreferenceFeedback, ProcessedOpportunity, UserFeedback


def apply_feedback(
    record: ProcessedOpportunity,
    feedback: UserFeedback | None,
) -> ProcessedOpportunity:
    record.feedback = feedback
    modifiers = {
        PreferenceFeedback.VERY_INTERESTED: 8.0,
        PreferenceFeedback.INTERESTED: 4.0,
        PreferenceFeedback.NOT_RELEVANT: -30.0,
    }
    modifier = modifiers.get(feedback.preference, 0.0) if feedback else 0.0
    record.personalized_score = max(0.0, min(100.0, record.score.final_score + modifier))
    return record


def assign_ranks(records: list[ProcessedOpportunity]) -> None:
    visible = [
        record
        for record in records
        if not record.excluded and not (record.feedback and record.feedback.hidden)
    ]
    visible.sort(
        key=lambda record: (
            record.personalized_score
            if record.personalized_score is not None
            else record.score.final_score
        ),
        reverse=True,
    )
    for rank, record in enumerate(visible, start=1):
        record.rank = rank
