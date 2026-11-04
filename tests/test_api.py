from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import api


CHECK_RESULT = {
    "claim": "COVID-19 vaccines reduce hospitalisation",
    "model": "liquid/lfm2.5-1.2b",
    "evidence_text": "[1] Evidence text.",
    "selected_evidence": [
        {
            "text": "Vaccines reduce hospitalisation.",
            "title": "Example source",
            "url": "https://example.com/source",
            "score": 0.81,
        }
    ],
    "retrieval": {
        "provider": "brave",
        "cached": False,
        "error": None,
        "results": [{"url": "https://example.com/source"}],
    },
    "label": "SUPPORTED",
    "reason": "The evidence supports the claim.",
    "raw_response": "LABEL: SUPPORTED\nREASON: The evidence supports the claim.",
    "retried": False,
    "latency_seconds": 0.1,
    "bert": None,
}

COMPARE_RESULT = {
    "claim": CHECK_RESULT["claim"],
    "evidence_bundle": {
        "evidence_text": CHECK_RESULT["evidence_text"],
        "selected": CHECK_RESULT["selected_evidence"],
        "retrieval": CHECK_RESULT["retrieval"],
    },
    "models": [
        {
            "model": "liquid/lfm2.5-1.2b",
            "label": "SUPPORTED",
            "reason": "Supported.",
            "raw_response": "SUPPORTED",
            "retried": False,
            "latency_seconds": 0.1,
        },
        {
            "model": "qwen3-0.6b",
            "label": "REFUTED",
            "reason": "Refuted.",
            "raw_response": "REFUTED",
            "retried": False,
            "latency_seconds": 0.2,
        },
    ],
    "bert": None,
}


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(api.app)
        api._RATE_BUCKETS.clear()

    def test_health_reports_lm_studio(self) -> None:
        with patch.object(api.llm_client, "list_models", return_value=[{"id": "m"}]):
            with patch.object(
                api.llm_client, "list_chat_models", return_value=["m"]
            ):
                response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["lm_studio"]["reachable"])
        self.assertEqual(payload["lm_studio"]["chat_models"], ["m"])

    def test_check_requires_access_code(self) -> None:
        with patch.object(api.config, "ACCESS_CODE", "test-code-1234567890"):
            response = self.client.post(
                "/check", json={"claim": "COVID-19 vaccines reduce hospitalisation"}
            )
        self.assertEqual(response.status_code, 401)

    def test_check_requires_configured_access_code(self) -> None:
        with patch.object(api.config, "ACCESS_CODE", ""):
            response = self.client.post(
                "/check",
                json={"claim": "COVID-19 vaccines reduce hospitalisation"},
                headers={"X-Access-Code": "anything"},
            )
        self.assertEqual(response.status_code, 503)

    def test_check_rejects_short_access_code(self) -> None:
        with patch.object(api.config, "ACCESS_CODE", "short"):
            response = self.client.post(
                "/check",
                json={"claim": "COVID-19 vaccines reduce hospitalisation"},
                headers={"X-Access-Code": "short"},
            )
        self.assertEqual(response.status_code, 503)

    def test_local_demo_bypasses_access_code_for_loopback(self) -> None:
        with patch.object(api.config, "LOCAL_DEMO", True):
            with patch.object(api, "_is_loopback", return_value=True):
                with patch.object(
                    api.pipeline, "check_claim", return_value=CHECK_RESULT
                ):
                    response = self.client.post(
                        "/check",
                        json={"claim": "COVID-19 vaccines reduce hospitalisation"},
                    )
        self.assertEqual(response.status_code, 200)

    def test_local_demo_does_not_bypass_external_requests(self) -> None:
        with patch.object(api.config, "LOCAL_DEMO", True):
            with patch.object(api, "_is_loopback", return_value=False):
                response = self.client.post(
                    "/check",
                    json={"claim": "COVID-19 vaccines reduce hospitalisation"},
                )
        self.assertEqual(response.status_code, 401)

    def test_static_frontend_is_served(self) -> None:
        response = self.client.get("/ui/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Factly", response.text)

    def test_oversized_body_is_rejected(self) -> None:
        with patch.object(api.config, "ACCESS_CODE", "test-code-1234567890"):
            response = self.client.post(
                "/check",
                content=b"x" * (api.MAX_REQUEST_BYTES + 1),
                headers={"X-Access-Code": "test-code-1234567890"},
            )
        self.assertEqual(response.status_code, 413)

    def test_check_returns_serialized_result(self) -> None:
        with patch.object(api.config, "ACCESS_CODE", "test-code-1234567890"):
            with patch.object(api.pipeline, "check_claim", return_value=CHECK_RESULT):
                response = self.client.post(
                    "/check",
                    json={"claim": "COVID-19 vaccines reduce hospitalisation"},
                    headers={"X-Access-Code": "test-code-1234567890"},
                )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "check")
        self.assertEqual(payload["models"][0]["label"], "SUPPORTED")
        self.assertEqual(payload["evidence"]["provider"], "brave")
        self.assertEqual(payload["evidence"]["selected"][0]["title"], "Example source")

    def test_compare_returns_two_models(self) -> None:
        with patch.object(api.config, "ACCESS_CODE", "test-code-1234567890"):
            with patch.object(
                api.pipeline, "compare_models", return_value=COMPARE_RESULT
            ):
                response = self.client.post(
                    "/compare",
                    json={
                        "claim": "COVID-19 vaccines reduce hospitalisation",
                        "primary_model": "liquid/lfm2.5-1.2b",
                        "secondary_model": "qwen3-0.6b",
                    },
                    headers={"X-Access-Code": "test-code-1234567890"},
                )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "compare")
        self.assertEqual(len(payload["models"]), 2)
        self.assertEqual(payload["models"][1]["label"], "REFUTED")

    def test_long_claim_is_rejected(self) -> None:
        with patch.object(api.config, "ACCESS_CODE", "test-code-1234567890"):
            response = self.client.post(
                "/check",
                json={"claim": "x" * (api.config.API_MAX_CLAIM_CHARS + 1)},
                headers={"X-Access-Code": "test-code-1234567890"},
            )
        self.assertEqual(response.status_code, 422)

    def test_rate_limit(self) -> None:
        with patch.object(api.config, "ACCESS_CODE", "test-code-1234567890"):
            with patch.object(api.config, "API_RATE_LIMIT", 1):
                with patch.object(
                    api.pipeline, "check_claim", return_value=CHECK_RESULT
                ):
                    first = self.client.post(
                        "/check",
                        json={"claim": "COVID-19 vaccines reduce hospitalisation"},
                        headers={"X-Access-Code": "test-code-1234567890"},
                    )
                    second = self.client.post(
                        "/check",
                        json={"claim": "COVID-19 vaccines reduce hospitalisation"},
                        headers={"X-Access-Code": "test-code-1234567890"},
                    )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)

    def test_rate_limit_counts_failed_auth_attempts(self) -> None:
        with patch.object(api.config, "ACCESS_CODE", "test-code-1234567890"):
            with patch.object(api.config, "API_RATE_LIMIT", 1):
                first = self.client.post(
                    "/check",
                    json={"claim": "COVID-19 vaccines reduce hospitalisation"},
                    headers={"X-Access-Code": "wrong-code-000000"},
                )
                second = self.client.post(
                    "/check",
                    json={"claim": "COVID-19 vaccines reduce hospitalisation"},
                    headers={"X-Access-Code": "test-code-1234567890"},
                )
        self.assertEqual(first.status_code, 401)
        self.assertEqual(second.status_code, 429)

    def test_cors_preflight(self) -> None:
        response = self.client.options(
            "/check",
            headers={
                "Origin": "https://darkstrike03.github.io",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "X-Access-Code, Content-Type",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "https://darkstrike03.github.io",
        )

    def test_evaluation_summary(self) -> None:
        response = self.client.get("/evaluation/summary")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreaterEqual(len(payload["gold"]), 1)
        self.assertGreaterEqual(len(payload["retrieval_sample"]), 1)

    def test_models_uses_fallbacks(self) -> None:
        with patch.object(api.llm_client, "list_chat_models", return_value=["m"]):
            response = self.client.get("/models")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("m", payload["models"])
        self.assertIn(api.config.DEFAULT_MODEL, payload["models"])
        self.assertIn(api.config.SECOND_MODEL, payload["models"])


if __name__ == "__main__":
    unittest.main()
