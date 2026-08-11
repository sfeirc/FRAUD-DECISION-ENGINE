from fraud_engine.decisioning import CostAssumptions, DecisionEngine, DecisionThresholds
from fraud_engine.domain import Decision


def test_threshold_boundaries() -> None:
    engine = DecisionEngine(thresholds=DecisionThresholds(review=0.4, decline=0.8))
    assert engine.decide(0.39) is Decision.APPROVE
    assert engine.decide(0.4) is Decision.REVIEW
    assert engine.decide(0.8) is Decision.DECLINE


def test_higher_false_positive_cost_cannot_make_decline_threshold_lower() -> None:
    scores = [0.05, 0.15, 0.35, 0.55, 0.75, 0.95]
    labels = [0, 0, 0, 1, 0, 1]
    amounts = [100.0] * len(scores)
    low = DecisionEngine(CostAssumptions(false_positive_decline_cost=5)).optimize(
        scores, labels, amounts
    )
    high = DecisionEngine(CostAssumptions(false_positive_decline_cost=100)).optimize(
        scores, labels, amounts
    )
    assert high.decline >= low.decline


def test_cost_breakdown_reconciles_total() -> None:
    engine = DecisionEngine(thresholds=DecisionThresholds(review=0.4, decline=0.8))
    cost = engine.evaluate([0.1, 0.5, 0.9], [1, 0, 0], [100, 100, 100])
    assert cost.total == sum(
        [cost.fraud_loss, cost.false_positive_cost, cost.manual_review_cost, cost.operational_cost]
    )


def test_threshold_optimization_respects_review_capacity() -> None:
    scores = [index / 100 for index in range(1, 100)]
    labels = [int(index % 10 == 0) for index in range(1, 100)]
    amounts = [100.0] * len(scores)
    engine = DecisionEngine(CostAssumptions(max_review_rate=0.03))
    engine.optimize(scores, labels, amounts)
    review_rate = sum(engine.decide(score) is Decision.REVIEW for score in scores) / len(scores)
    assert review_rate <= 0.03
