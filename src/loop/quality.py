"""
Quality checker - determines when the loop should stop based on quality metrics.
"""

from typing import List


class QualityChecker:
    """Evaluates quality-based stop criteria for the autonomous loop."""
    
    def __init__(self, force_iterations: bool = False):
        self.force_iterations = force_iterations
    
    def should_continue(self, iteration: int, quality_history: List[int]) -> bool:
        """Check if loop should continue based on quality convergence."""
        if self.force_iterations or len(quality_history) < 1:
            return True
        
        # Require at least 2 iterations before stopping for quality
        if iteration < 2:
            return True
        
        latest_quality = quality_history[-1]
        
        # Criterion 1: Quality Score 100/100 → immediate STOP
        if latest_quality == 100:
            print(f"\n🎉 Quality Score 100/100 reached! Loop completed.")
            return False
        
        # Criterion 2: Convergence - same score for 2 consecutive iterations
        if len(quality_history) >= 2:
            prev_quality = quality_history[-2]
            if latest_quality == prev_quality and latest_quality >= 80:
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
            # Criterion 1: Quality Score 100/100 → STOP
            if quality_score == 100:
                print(f"\n🎉 Quality Score 100/100! Perfect machine.")
                return True
            
            # Criterion 2: Quality ≥ 90 AND 0 critical issues → STOP
            if quality_score >= 90 and critical_issues == 0:
                print(f"\n✅ Quality Score {quality_score}/100 with 0 critical issues. Sufficient quality.")
                return True
        
        return False