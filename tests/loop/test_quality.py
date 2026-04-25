"""Tests for loop/quality.py"""

import pytest
from loop.quality import QualityChecker


class TestQualityChecker:
    def test_force_iterations_always_continues(self):
        checker = QualityChecker(force_iterations=True)
        assert checker.should_continue(1, [80, 90, 100], 0) is True
        assert checker.should_continue(10, [100], 0) is True

    def test_continues_on_first_iteration(self):
        checker = QualityChecker()
        assert checker.should_continue(1, [80], 0) is True

    def test_stops_at_100_with_no_critical_issues(self, capsys):
        checker = QualityChecker()
        result = checker.should_continue(2, [80, 100], 0)
        assert result is False
        captured = capsys.readouterr()
        assert "100/100" in captured.out

    def test_continues_at_100_with_critical_issues(self, capsys):
        checker = QualityChecker()
        result = checker.should_continue(2, [80, 100], 3)
        assert result is True
        captured = capsys.readouterr()
        assert "critical issues" in captured.out

    def test_stops_on_convergence_above_80(self, capsys):
        checker = QualityChecker()
        result = checker.should_continue(3, [80, 85, 85], 0)
        assert result is False
        captured = capsys.readouterr()
        assert "Convergence" in captured.out

    def test_continues_on_convergence_below_80(self):
        checker = QualityChecker()
        result = checker.should_continue(3, [70, 70, 70], 0)
        assert result is True

    def test_continues_on_convergence_with_critical_issues(self):
        checker = QualityChecker()
        result = checker.should_continue(3, [85, 85, 85], 1)
        assert result is True

    def test_check_quality_stop_at_100_no_issues(self, capsys):
        checker = QualityChecker()
        result = checker.check_quality_stop(
            {"quality_score": 100}, {"critical_issues": []}, 2
        )
        assert result is True

    def test_check_quality_stop_at_90_no_issues(self, capsys):
        checker = QualityChecker()
        result = checker.check_quality_stop(
            {"quality_score": 90}, {"critical_issues": []}, 2
        )
        assert result is True

    def test_check_quality_stop_below_90(self):
        checker = QualityChecker()
        result = checker.check_quality_stop(
            {"quality_score": 80}, {"critical_issues": []}, 2
        )
        assert result is False

    def test_check_quality_stop_at_100_with_issues(self):
        checker = QualityChecker()
        result = checker.check_quality_stop(
            {"quality_score": 100}, {"critical_issues": [{"id": "CRIT-001"}]}, 2
        )
        assert result is False

    def test_check_quality_stop_before_iteration_2(self):
        checker = QualityChecker()
        result = checker.check_quality_stop(
            {"quality_score": 100}, {"critical_issues": []}, 1
        )
        assert result is False