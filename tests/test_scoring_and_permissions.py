import app


def test_get_rating_bands():
    assert app.get_rating(4.6) == "Outstanding"
    assert app.get_rating(4.1) == "Exceeds Expectations"
    assert app.get_rating(3.4) == "Meets Expectations"
    assert app.get_rating(2.9) == "Needs Improvement"


def test_calculate_weighted_score_uses_category_average():
    kpi_scores = [
        {"metric": "A", "category": "Operational Excellence", "score": 5},
        {"metric": "B", "category": "Operational Excellence", "score": 3},
        {"metric": "C", "category": "Delivery & Timelines", "score": 4},
        {"metric": "D", "category": "Quality & Compliance", "score": 2},
        {"metric": "E", "category": "Documentation & Process", "score": 5},
        {"metric": "F", "category": "Innovation / Improvement", "score": 4},
        {"metric": "G", "category": "Collaboration & Communication", "score": 5},
    ]
    final_score, breakdown = app.calculate_weighted_score(kpi_scores)
    # Operational avg = (5+3)/2 = 4 -> 1.2
    # Delivery avg = 4 -> 1.0
    # Quality avg = 2 -> 0.4
    # Documentation avg = 5 -> 0.5
    # Innovation avg = 4 -> 0.4
    # Collaboration avg = 5 -> 0.25
    # Total = 3.75
    assert final_score == 3.75
    assert not breakdown.empty


def test_can_edit_scorecard_employee_own_draft(monkeypatch):
    monkeypatch.setattr(app, "is_cycle_closed", lambda cycle: False)
    record = {
        "review_cycle": "Q1",
        "status": "Draft",
        "created_by": "alice",
    }
    allowed, reason = app.can_edit_scorecard(record, "Employee", "alice")
    assert allowed is True
    assert reason == ""


def test_can_edit_scorecard_employee_not_owner(monkeypatch):
    monkeypatch.setattr(app, "is_cycle_closed", lambda cycle: False)
    record = {
        "review_cycle": "Q1",
        "status": "Draft",
        "created_by": "bob",
    }
    allowed, reason = app.can_edit_scorecard(record, "Employee", "alice")
    assert allowed is False
    assert "own records" in reason


def test_can_edit_scorecard_manager_team_scoped(monkeypatch):
    monkeypatch.setattr(app, "is_cycle_closed", lambda cycle: False)
    monkeypatch.setattr(app, "fetch_team_usernames", lambda manager: ["emp1", "emp2"])
    record = {
        "review_cycle": "Q2",
        "status": "Submitted",
        "created_by": "emp1",
    }
    allowed, reason = app.can_edit_scorecard(record, "Manager", "manager1")
    assert allowed is True
    assert reason == ""


def test_can_edit_scorecard_blocks_closed_cycle(monkeypatch):
    monkeypatch.setattr(app, "is_cycle_closed", lambda cycle: True)
    record = {
        "review_cycle": "Q3",
        "status": "Draft",
        "created_by": "alice",
    }
    allowed, reason = app.can_edit_scorecard(record, "Admin", "admin")
    assert allowed is False
    assert "closed" in reason.lower()


def test_can_edit_scorecard_blocks_finalized(monkeypatch):
    monkeypatch.setattr(app, "is_cycle_closed", lambda cycle: False)
    record = {
        "review_cycle": "Q4",
        "status": "Finalized",
        "created_by": "alice",
    }
    allowed, reason = app.can_edit_scorecard(record, "Admin", "admin")
    assert allowed is False
    assert "locked" in reason.lower()
