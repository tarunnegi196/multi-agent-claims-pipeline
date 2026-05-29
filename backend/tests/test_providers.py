"""
Tests for GeminiVisionProvider and GeminiClassifierProvider.

All Gemini API calls are mocked — no network, no API key required.
Tests verify: happy path, timeout fallback, bad JSON fallback, no-key fallback.
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.document import DocumentType


# ── GeminiVisionProvider ─────────────────────────────────────────────────────

class TestGeminiVisionProvider:

    def _make_provider(self, api_key: str = "test-key"):
        """Build a provider with a mocked Gemini model."""
        with patch("app.config.settings") as mock_settings:
            mock_settings.gemini_api_key = api_key
            with patch("google.generativeai.configure"), \
                 patch("google.generativeai.GenerativeModel") as mock_model_cls:
                mock_model = MagicMock()
                mock_model_cls.return_value = mock_model
                from app.providers.gemini_vision import GeminiVisionProvider
                provider = GeminiVisionProvider.__new__(GeminiVisionProvider)
                provider._model = mock_model
                provider._ready = bool(api_key)
                return provider, mock_model

    async def test_happy_path_returns_extracted_doc(self):
        provider, mock_model = self._make_provider()
        payload = {
            "patient_name": "Rajesh Kumar",
            "date": "2024-11-01",
            "doctor_name": "Dr. Arun Sharma",
            "doctor_registration": "KA/45678/2015",
            "diagnosis": "Viral Fever",
            "medicines": ["Paracetamol 650mg"],
            "tests_ordered": [],
            "hospital_name": "City Clinic",
            "bill_number": None,
            "line_items": [{"description": "Consultation", "amount": 1000}],
            "total_amount": 1000,
            "lab_name": None,
            "test_results": {},
        }
        mock_response = MagicMock()
        mock_response.text = json.dumps(payload)
        mock_model.generate_content.return_value = mock_response

        result = await provider.extract("F001", DocumentType.PRESCRIPTION,
                                        b"fake_image", "image/jpeg")

        assert result.patient_name == "Rajesh Kumar"
        assert result.diagnosis == "Viral Fever"
        assert result.extraction_method == "gemini_vision"
        assert result.overall_confidence >= 0.60

    async def test_no_api_key_returns_fallback(self):
        from app.providers.gemini_vision import GeminiVisionProvider
        provider = GeminiVisionProvider.__new__(GeminiVisionProvider)
        provider._model = None
        provider._ready = False

        result = await provider.extract("F002", DocumentType.HOSPITAL_BILL,
                                        b"bytes", "image/jpeg")

        assert result.overall_confidence <= 0.30
        assert "EXTRACTION_FALLBACK" in result.flags
        assert result.extraction_method == "gemini_vision_fallback"

    async def test_timeout_returns_fallback(self):
        provider, mock_model = self._make_provider()

        async def slow_call(*args, **kwargs):
            await asyncio.sleep(100)

        with patch.object(provider, "_call_gemini", side_effect=asyncio.TimeoutError):
            result = await provider.extract("F003", DocumentType.LAB_REPORT,
                                            b"bytes", "image/jpeg")

        assert result.overall_confidence <= 0.30
        assert result.extraction_method == "gemini_vision_fallback"

    async def test_invalid_json_triggers_fallback(self):
        provider, mock_model = self._make_provider()
        mock_response = MagicMock()
        mock_response.text = "not json at all {{{"
        mock_model.generate_content.return_value = mock_response

        # _call_gemini raises JSONDecodeError → retry exhausted → reraise → extract catches
        result = await provider.extract("F004", DocumentType.PRESCRIPTION,
                                        b"bytes", "image/jpeg")

        assert result.overall_confidence <= 0.30

    async def test_markdown_fence_stripped(self):
        provider, mock_model = self._make_provider()
        payload = {"patient_name": "Test", "date": None, "doctor_name": None,
                   "doctor_registration": None, "diagnosis": "Fever",
                   "medicines": [], "tests_ordered": [], "hospital_name": None,
                   "bill_number": None, "line_items": [], "total_amount": 500,
                   "lab_name": None, "test_results": {}}
        mock_response = MagicMock()
        mock_response.text = f"```json\n{json.dumps(payload)}\n```"
        mock_model.generate_content.return_value = mock_response

        result = await provider.extract("F005", DocumentType.HOSPITAL_BILL,
                                        b"bytes", "image/jpeg")

        assert result.patient_name == "Test"
        assert result.total_amount == 500.0


# ── GeminiClassifierProvider ─────────────────────────────────────────────────

class TestGeminiClassifierProvider:

    def _make_provider(self):
        with patch("app.config.settings") as mock_settings:
            mock_settings.gemini_api_key = "test-key"
            with patch("google.generativeai.configure"), \
                 patch("google.generativeai.GenerativeModel") as mock_model_cls:
                mock_model = MagicMock()
                mock_model_cls.return_value = mock_model
                from app.providers.gemini_classifier import GeminiClassifierProvider
                provider = GeminiClassifierProvider.__new__(GeminiClassifierProvider)
                provider._model = mock_model
                provider._ready = True
                return provider, mock_model

    async def test_classifies_prescription(self):
        provider, mock_model = self._make_provider()
        mock_response = MagicMock()
        mock_response.text = '{"document_type": "PRESCRIPTION", "confidence": 0.95}'
        mock_model.generate_content.return_value = mock_response

        dtype, conf, quality = await provider.classify("F001", b"img", "image/jpeg")

        assert dtype == DocumentType.PRESCRIPTION
        assert conf == pytest.approx(0.95)

    async def test_unknown_type_in_response_maps_to_unknown(self):
        provider, mock_model = self._make_provider()
        mock_response = MagicMock()
        mock_response.text = '{"document_type": "BANANA", "confidence": 0.9}'
        mock_model.generate_content.return_value = mock_response

        dtype, conf, quality = await provider.classify("F002", b"img", "image/jpeg")

        assert dtype == DocumentType.UNKNOWN

    async def test_no_key_returns_unknown(self):
        from app.providers.gemini_classifier import GeminiClassifierProvider
        provider = GeminiClassifierProvider.__new__(GeminiClassifierProvider)
        provider._model = None
        provider._ready = False

        dtype, conf, quality = await provider.classify("F003", b"img", "image/jpeg")

        assert dtype == DocumentType.UNKNOWN
        assert conf <= 0.35

    async def test_timeout_returns_unknown(self):
        provider, mock_model = self._make_provider()
        with patch.object(provider, "_call_gemini", side_effect=asyncio.TimeoutError):
            dtype, conf, quality = await provider.classify("F004", b"img", "image/jpeg")
        assert dtype == DocumentType.UNKNOWN
