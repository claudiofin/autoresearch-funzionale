"""
Quality checker - determines when the loop should stop based on quality metrics.
"""

from typing import List


class QualityChecker:
    """Evaluates quality-based stop criteria for the autonomous loop."""
    
    def __init__(self, force_iterations: bool = False):
        self.force_iterations = force_iterations
    
    def should_continue(self, iteration: int, quality_history: List[int], critical_issues: int = 0) -> bool:
        """Check if loop should continue based on quality convergence.
        
        Args:
            iteration: Current iteration number
            quality_history: List of quality scores from each iteration
            critical_issues: Number of critical issues from the critic (0 if not available)
        
        Returns:
            True if loop should continue, False if it should stop
        """
        if self.force_iterations or len(quality_history) < 1:
            return True
        
        # Require at least 2 iterations before stopping for quality
        if iteration < 2:
            return True
        
        latest_quality = quality_history[-1]
        
        # Criterion 1: Quality Score 100/100 AND 0 critical issues → immediate STOP
        # IMPORTANT: Don't stop at 100/100 if there are still critical issues!
        if latest_quality == 100 and critical_issues == 0:
            print(f"\n🎉 Quality Score 100/100 reached with 0 critical issues! Loop completed.")
            return False
        elif latest_quality == 100 and critical_issues > 0:
            print(f"\n⚠️  Quality Score 100/100 but {critical_issues} critical issues remain — continuing...")
        
        # Criterion 2: Convergence - same score for 2 consecutive iterations (only if no critical issues)
        if len(quality_history) >= 2:
            prev_quality = quality_history[-2]
            if latest_quality == prev_quality and latest_quality >= 80 and critical_issues == 0:
                print(f"\n🎯 Convergence reached: Quality Score {latest_quality}/100 stable for 2 iterations.")
                return False
        
        return True
    
    def check_quality_stop(self, validator_result: dict, critic_result: dict, iteration: int) -> bool:
        """Check if loop should stop based on Quality Score and critical issues.
        
        Returns True if loop should stop.
        """
        if self.force_iterations:
            return False
        
        # Require at least 2 iterations before stopping for quality
        if iteration < 2:
            return False
        
        quality_score = validator_result.get("quality_score")
        critical_issues = critic_result.get("critical_issues", 0)
        
        if quality_score is not None:
            # Criterion 1: Quality Score 100/100 AND 0 critical issues → STOP
            # IMPORTANT: Don't stop at 100/100 if there are still critical issues!
            if quality_score == 100 and critical_issues == 0:
                print(f"\n🎉 Quality Score 100/100! Perfect machine with 0 critical issues.")
                return True
            elif quality_score == 100 and critical_issues > 0:
                print(f"\n⚠️  Quality Score 100/100 but {critical_issues} critical issues — not stopping.")
            
            # Criterion 2: Quality ≥ 90 AND 0 critical issues → STOP
            if quality_score >= 90 and critical_issues == 0:
                print(f"\n✅ Quality Score {quality_score}/100 with 0 critical issues. Sufficient quality.")
                return True
        
        return False
