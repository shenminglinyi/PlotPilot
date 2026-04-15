from application.world.services.worldbuilding_review_committee import aggregate_reviews


def test_aggregate_reviews_redline_veto_and_research_rework():
    reviews = [
        {
            "reviewer_role": "fact",
            "verdict": "rework",
            "score": 60,
            "redlines_triggered": ["fact_conflict"],
            "needs_research_rework": True,
            "issues": [],
            "fix_instructions": ["x"],
        },
        {
            "reviewer_role": "genre",
            "verdict": "approve",
            "score": 80,
            "redlines_triggered": [],
            "needs_research_rework": False,
            "issues": [],
            "fix_instructions": [],
        },
        {
            "reviewer_role": "reader",
            "verdict": "approve",
            "score": 80,
            "redlines_triggered": [],
            "needs_research_rework": False,
            "issues": [],
            "fix_instructions": [],
        },
    ]
    bundle = aggregate_reviews(reviews)
    assert bundle["redline_veto"] is True
    assert bundle["final_verdict"] in ("rework", "reject")
    assert bundle["needs_research_rework"] is True

