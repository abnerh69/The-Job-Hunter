from jobhunter.db.models import Job
from jobhunter.application.variant_selector import recommend_cv_variant


def test_recommend_ai_python_via_flag():
    job = Job(
        title="AI Engineer",
        description="Looking for an AI enthusiast.",
        score_data={
            "valid": True,
            "role": {
                "is_ai_ml_role": True,
                "is_flutter_role": False,
                "is_full_stack": False,
                "primary_stack_match": ["Python", "PyTorch"],
            },
        },
    )
    recommendation = recommend_cv_variant(job)
    assert recommendation.variant_name == "ai_python"
    assert recommendation.confidence >= 0.8
    assert "explicitly flagged" in recommendation.reasoning


def test_recommend_ai_python_via_stack():
    job = Job(
        title="Software Engineer",
        description="Generic description.",
        score_data={
            "valid": True,
            "role": {
                "is_ai_ml_role": False,
                "is_flutter_role": False,
                "is_full_stack": False,
                "primary_stack_match": ["Python", "LLM", "LangChain"],
            },
        },
    )
    recommendation = recommend_cv_variant(job)
    assert recommendation.variant_name == "ai_python"
    assert recommendation.confidence >= 0.8
    assert "Stack match" in recommendation.reasoning


def test_recommend_flutter_via_flag():
    job = Job(
        title="Mobile Developer",
        description="Build mobile apps.",
        score_data={
            "valid": True,
            "role": {
                "is_ai_ml_role": False,
                "is_flutter_role": True,
                "is_full_stack": False,
                "primary_stack_match": ["Flutter", "Dart"],
            },
        },
    )
    recommendation = recommend_cv_variant(job)
    assert recommendation.variant_name == "flutter"
    assert recommendation.confidence >= 0.8
    assert "explicitly flagged" in recommendation.reasoning


def test_recommend_flutter_via_stack():
    job = Job(
        title="Software Engineer",
        description="Generic description.",
        score_data={
            "valid": True,
            "role": {
                "is_ai_ml_role": False,
                "is_flutter_role": False,
                "is_full_stack": False,
                "primary_stack_match": ["Flutter"],
            },
        },
    )
    recommendation = recommend_cv_variant(job)
    assert recommendation.variant_name == "flutter"
    assert recommendation.confidence >= 0.8
    assert "Stack match" in recommendation.reasoning


def test_recommend_fullstack_via_flag():
    job = Job(
        title="Software Engineer",
        description="Build web apps.",
        score_data={
            "valid": True,
            "role": {
                "is_ai_ml_role": False,
                "is_flutter_role": False,
                "is_full_stack": True,
                "primary_stack_match": ["React", "Node.js"],
            },
        },
    )
    recommendation = recommend_cv_variant(job)
    assert recommendation.variant_name == "fullstack"
    assert recommendation.confidence >= 0.8
    assert "explicitly flagged" in recommendation.reasoning


def test_recommend_fullstack_ambiguous_with_score_data():
    job = Job(
        title="Generalist Engineer",
        description="Do everything.",
        score_data={
            "valid": True,
            "role": {
                "is_ai_ml_role": False,
                "is_flutter_role": False,
                "is_full_stack": False,
                "primary_stack_match": ["C++", "Embedded"],
            },
        },
    )
    recommendation = recommend_cv_variant(job)
    assert recommendation.variant_name == "fullstack"
    assert recommendation.confidence == 0.5
    assert "No specific stack match" in recommendation.reasoning


def test_recommend_via_keywords_fallback_flutter():
    job = Job(
        title="Mobile Developer (Flutter)",
        description="We need someone who knows Dart and Flutter.",
        score_data=None,
    )
    recommendation = recommend_cv_variant(job)
    assert recommendation.variant_name == "flutter"
    assert recommendation.confidence <= 0.5
    assert "Heuristic match" in recommendation.reasoning


def test_recommend_via_keywords_fallback_ai_python():
    job = Job(
        title="Python Developer",
        description="Experience with LLMs and AI is a plus.",
        score_data={},
    )
    recommendation = recommend_cv_variant(job)
    assert recommendation.variant_name == "ai_python"
    assert recommendation.confidence <= 0.5
    assert "Heuristic match" in recommendation.reasoning


def test_recommend_absolute_fallback():
    job = Job(
        title="Software Engineer",
        description="Just a job.",
        score_data=None,
    )
    recommendation = recommend_cv_variant(job)
    assert recommendation.variant_name == "fullstack"
    assert recommendation.confidence <= 0.5
    assert "No structured scoring data or clear keyword matches" in recommendation.reasoning
