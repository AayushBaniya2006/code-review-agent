import unittest

from app.api.routes import AuditResponse


class TestAuditResponseModel(unittest.TestCase):
    def test_response_shape(self):
        payload = {
            "audit_id": "test-id",
            "status": "completed",
            "summary": {
                "overall_score": 70,
                "risk_level": "medium",
                "total_findings": 2,
                "critical_findings": 0,
            },
            "audits": {"security": {"score": 70, "findings": []}},
            "synthesis": {"executive_summary": "OK", "verdict": "APPROVE_WITH_CHANGES"},
            "metadata": {
                "files_analyzed": 1,
                "lines_added": 2,
                "lines_removed": 1,
                "languages": ["python"],
            },
        }

        model = AuditResponse(**payload)
        self.assertEqual(model.status, "completed")


if __name__ == "__main__":
    unittest.main()
