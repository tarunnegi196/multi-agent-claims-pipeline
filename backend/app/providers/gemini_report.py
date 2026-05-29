"""
GeminiReportProvider — synthesises a human-readable narrative + next-best-actions
from the structured Decision and pipeline trace.

The deterministic policy engine has already produced the verdict and a short
explanation. This provider takes those facts and turns them into:
  • a 2–3 sentence narrative the operations team / member can read
  • a confidence_reasoning paragraph explaining WHY confidence is what it is
  • a prioritised list of next_best_actions tailored to the decision

The LLM does NOT change the verdict, amount, or rejection reasons. It only
rephrases and prioritises action items. On failure the agent falls back to
templated text so the pipeline never blocks on the LLM.
"""
import asyncio
import json
import logging
from typing import Optional

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings

logger = logging.getLogger(__name__)


_REPORT_PROMPT = """\
You are an explainability layer for an Indian health-insurance claims engine.
The verdict, approved amount and rejection reasons have ALREADY been decided
by a deterministic policy engine — do not change them.

Your job: write the human-facing explanation.

Return ONLY valid JSON — no explanation, no markdown fences:
{{
  "narrative": "2-3 sentences explaining the outcome in plain English. Reference the policy clause that drove it.",
  "confidence_reasoning": "1-2 sentences explaining WHY confidence is at the given level — what was clear vs ambiguous.",
  "next_best_actions": [
    "Imperative action 1 (member or ops team can do)",
    "Imperative action 2",
    "..."
  ]
}}

Rules:
  • Tone: factual, empathetic, no jargon. Address the member when the action is
    on them (e.g., "Re-upload..."), the ops team when on them ("Manually
    verify...").
  • next_best_actions: 1-4 items, prioritised. Make them concrete and specific.
    - APPROVED: 1 item ("No further action — payout will be processed in N days")
    - PARTIAL:  2-3 items (explain deductions; offer appeal path if applicable)
    - REJECTED: 2-3 items (state the fix path; reference clause)
    - MANUAL_REVIEW: 3-4 items (what the reviewer must verify; what the member
      should expect; SLAs)
  • If consistency_flags or fraud_flags are present, surface them in the narrative.
  • If component_failures is non-empty, mention degraded processing.
  • NEVER promise a payout amount different from approved_amount.
  • NEVER change the rejection reasons; you may reference them.

Decision context:
{decision_json}

Claim context:
{claim_json}

Pipeline observations:
{observations_json}
"""

_TIMEOUT_SECONDS = 15


class GeminiReportProvider:
    """Generate narrative + next actions for a completed Decision."""

    def __init__(self) -> None:
        self._model = None
        self._ready = False
        if settings.gemini_api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=settings.gemini_api_key)
                self._model = genai.GenerativeModel(
                    model_name=settings.gemini_classifier_model,
                    generation_config={"response_mime_type": "application/json", "temperature": 0.3},
                )
                self._ready = True
                logger.info("GeminiReportProvider ready (model=%s)",
                            settings.gemini_classifier_model)
            except Exception as exc:
                logger.warning("GeminiReportProvider init failed: %s", exc)

    def is_available(self) -> bool:
        return self._ready

    async def synthesise(
        self,
        decision_dict: dict,
        claim_dict: dict,
        observations: dict,
    ) -> Optional[dict]:
        if not self._ready:
            return None
        try:
            return await asyncio.wait_for(
                self._call_gemini(decision_dict, claim_dict, observations),
                timeout=_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("[GEMINI-REPORT] timeout")
            return None
        except Exception as exc:
            logger.warning("[GEMINI-REPORT] failed: %s", exc)
            return None

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True,
    )
    async def _call_gemini(
        self, decision_dict: dict, claim_dict: dict, observations: dict,
    ) -> dict:
        prompt = _REPORT_PROMPT.format(
            decision_json=json.dumps(decision_dict, indent=2, default=str),
            claim_json=json.dumps(claim_dict, indent=2, default=str),
            observations_json=json.dumps(observations, indent=2, default=str),
        )
        logger.info("[GEMINI-REPORT] CALL  decision=%s  confidence=%.2f",
                    decision_dict.get("decision_type"), decision_dict.get("confidence", 0.0))

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

        # Sanitise
        narrative = str(data.get("narrative", "")).strip()
        reasoning = str(data.get("confidence_reasoning", "")).strip()
        actions = [str(a).strip() for a in (data.get("next_best_actions") or []) if a]

        logger.info("[GEMINI-REPORT] DONE  narrative_chars=%d  actions=%d",
                    len(narrative), len(actions))
        return {
            "narrative": narrative,
            "confidence_reasoning": reasoning,
            "next_best_actions": actions[:4],
        }


gemini_report = GeminiReportProvider()
