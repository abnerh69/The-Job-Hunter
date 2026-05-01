import uuid
from sqlalchemy.orm import Session
from jobhunter.analytics.ab_testing import select_variant, calculate_z_test
from jobhunter.db.models import ABTest
from jobhunter.db.enums import ABTestStatus


def test_select_variant_deterministic(session: Session) -> None:
    test_name = "test_prompt"
    variants = {"v1": 0.5, "v2": 0.5}
    ab_test = ABTest(
        name=test_name, variants=variants, metric_target="test_metric", status=ABTestStatus.ACTIVE
    )
    session.add(ab_test)
    session.commit()

    entity_id = uuid.uuid4()

    variant1 = select_variant(session, test_name, entity_id)
    variant2 = select_variant(session, test_name, entity_id)

    assert variant1 == variant2
    assert variant1 in variants


def test_select_variant_distribution(session: Session) -> None:
    test_name = "dist_test"
    variants = {"v1": 0.5, "v2": 0.5}
    ab_test = ABTest(
        name=test_name, variants=variants, metric_target="test_metric", status=ABTestStatus.ACTIVE
    )
    session.add(ab_test)
    session.commit()

    results = {"v1": 0, "v2": 0}
    for _ in range(1000):
        entity_id = uuid.uuid4()
        variant = select_variant(session, test_name, entity_id)
        results[variant] += 1

    # Check for ~50/50 distribution with 5% margin
    assert 450 <= results["v1"] <= 550
    assert 450 <= results["v2"] <= 550


def test_select_variant_no_active_test(session: Session) -> None:
    entity_id = uuid.uuid4()
    variant = select_variant(session, "non_existent", entity_id)
    assert variant == "default"


def test_calculate_z_test() -> None:
    # Large sample, clear difference
    p_val = calculate_z_test(0.1, 1000, 0.2, 1000)
    assert p_val < 0.05

    # Small sample, no difference
    p_val = calculate_z_test(0.1, 30, 0.12, 30)
    assert p_val > 0.05

    # Same proportions
    p_val = calculate_z_test(0.5, 100, 0.5, 100)
    assert p_val == 1.0
