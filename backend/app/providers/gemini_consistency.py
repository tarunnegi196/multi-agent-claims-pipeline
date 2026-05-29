"""
GeminiConsistencyProvider — semantic cross-document consistency analysis.

Given the structured fields extracted from every uploaded document in a single
claim, asks Gemini to verify they refer to the same patient / doctor / hospital
/ treatment date. Catches semantic matches a strict string compare would miss
("Rajesh Kumar" vs "R. Kumar", "Apollo Hospitals" vs "Apollo Hospital BLR").

Returns a structured verdict with per-dimension status and human-readable flags.
On any failure returns an empty verdict (consistency_flags=[]); the deterministic
patient-name halt in extractor.py still catches the hard mismatch case.
"""
import asyncio
import json
import logging
from typing import Optional

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings

logger = logging.getLogger(__name__)

_CONSISTENCY_PROMPT = """\
You are a fraud-detection analyst reviewing extracted fields from a SINGLE
insurance claim's uploaded documents. Verify whether all documents refer to
the SAME patient, doctor, hospital, and treatment episode.

Return ONLY valid JSON — no explanation, no markdown fences:
{{
  "patient_match": "MATCH" | "FUZZY_MATCH" | "MISMATCH" | "UNVERIFIABLE",
  "doctor_match":  "MATCH" | "FUZZY_MATCH" | "MISMATCH" | "UNVERIFIABLE" | "NOT_APPLICABLE",
  "hospital_match":"MATCH" | "FUZZY_MATCH" | "MISMATCH" | "UNVERIFIABLE" | "NOT_APPLICABLE",
  "date_match":    "MATCH" | "FUZZY_MATCH" | "MISMATCH" | "UNVERIFIABLE",
  "overall_consistent": true | false,
  "confidence": 0.0,
  "flags": ["short human-readable warning per mismatch or fuzzy issue"],
  "reasoning": "1-2 sentence summary of what you compared"
}}

Rules:
  MATCH        — identical or trivially equivalent (case/whitespace only).
  FUZZY_MATCH  — clearly same entity with minor variants (initials, abbreviations,
                 "Dr." prefix, branch suffix). Flag it but do NOT mark mismatch.
  MISMATCH     — different entities (e.g., "Rajesh Kumar" vs "Arjun Mehta",
                 dates >7 days apart for a single episode).
  UNVERIFIABLE — the field is missing in 2+ docs so no comparison is possible.
  NOT_APPLICABLE — only relevant when no prescription/bill is present.

For dates: documents from the same treatment episode should be within ~7 days.
If the spread is wider, that is a MISMATCH for the date dimension.

overall_consistent = true only if patient_match is MATCH or FUZZY_MATCH
                     AND date_match is not MISMATCH
                     AND no MISMATCH on doctor/hospital.

Documents to analyse:
{documents_json}
"""

_TIMEOUT_SECONDS = 12


class GeminiConsistencyProvider:
    """Cross-document semantic consistency check via Gemini."""

    def __init__(self) -> None:
        self._model = None
        self._ready = False
        if settings.gemini_api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=settings.gemini_api_key)
                self._model = genai.GenerativeModel(
                    model_name=settings.gemini_classifier_model,
                    generation_config={"response_mime_type": "application/json", "temperature": 0.0},
                )
                self._ready = True
                logger.info("GeminiConsistencyProvider ready (model=%s)",
                            settings.gemini_classifier_model)
            except Exception as exc:
                logger.warning("GeminiConsistencyProvider init failed: %s", exc)

    def is_available(self) -> bool:
        return self._ready

    async def check(self, docs_for_check: list[dict]) -> Optional[dict]:
        """
        docs_for_check: list of dicts like
            {"file_id": ..., "doc_type": ..., "patient_name": ..., "date": ...,
             "doctor_name": ..., "hospital_name": ..., "doctor_registration": ...}

        Returns the parsed verdict dict (see prompt JSON shape) or None on failure.
        """
        if not self._ready:
            return None
        if len(docs_for_check) < 2:
            return None
        try:
            return await asyncio.wait_for(
                self._call_gemini(docs_for_check),
                timeout=_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("[GEMINI-CONSISTENCY] timeout")
            return None
        except Exception as exc:
            logger.warning("[GEMINI-CONSISTENCY] failed: %s", exc)
            return None

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True,
    )
    async def _call_gemini(self, docs_for_check: list[dict]) -> dict:
        prompt = _CONSISTENCY_PROMPT.format(
            documents_json=json.dumps(docs_for_check, indent=2)
        )
        logger.info("[GEMINI-CONSISTENCY] CALL  docs=%d", len(docs_for_check))

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._model.generate_content([prompt]),
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        data = json.loads(raw)

        logger.info(
            "[GEMINI-CONSISTENCY] DONE  consistent=%s  patient=%s  doctor=%s  "
            "hospital=%s  date=%s  flags=%d",
            data.get("overall_consistent"),
            data.get("patient_match"),
            data.get("doctor_match"),
            data.get("hospital_match"),
            data.get("date_match"),
            len(data.get("flags") or []),
        )
        return data


gemini_consistency = GeminiConsistencyProvider()
