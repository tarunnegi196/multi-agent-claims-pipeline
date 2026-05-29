"""
PDF report builder — generates a single-page-per-section PDF for a completed claim.

Layout:
  1. Header banner with verdict + confidence
  2. Claim metadata (member, category, dates, amounts)
  3. Decision Q&A table (each pipeline question, the answer, the reason)
  4. Amount breakdown (when present)
  5. Documents processed (type, quality)
  6. Fraud signals (when present)
  7. Pipeline trace summary grouped by agent

Pure presentation — no business logic. Reads from the stored FinalOutput only.
"""
from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.decision import Decision, DecisionType
from app.models.trace import TraceEvent

# ── Plum brand colours (HexColor) ────────────────────────────────────────────
PLUM_MAROON   = colors.HexColor("#570e40")
PLUM_DARK     = colors.HexColor("#11040d")
PLUM_PINK     = colors.HexColor("#bea0b3")
PLUM_OFFWHITE = colors.HexColor("#fffaf2")
PLUM_BORDER   = colors.HexColor("#ced5dd")
PLUM_GREEN    = colors.HexColor("#92bd33")
PLUM_AMBER    = colors.HexColor("#ffbf21")
PLUM_RED      = colors.HexColor("#ff4052")
PLUM_GREY     = colors.HexColor("#55657d")

_DECISION_COLOR = {
    DecisionType.APPROVED:      PLUM_GREEN,
    DecisionType.PARTIAL:       PLUM_AMBER,
    DecisionType.REJECTED:      PLUM_RED,
    DecisionType.MANUAL_REVIEW: PLUM_AMBER,
}

_AGENT_LABELS = {
    "IntakeAgent":           "1. Intake",
    "DocClassifierAgent":    "2. Classifier",
    "DocVerifierAgent":      "3. Verifier",
    "ExtractionAgent":       "4. Extraction",
    "ConsistencyAgent":      "5. Consistency",
    "FraudScreenAgent":      "6. Fraud Screen",
    "DecisionComposerAgent": "7. Decision",
    "ReportAgent":           "8. Report",
}

_AGENT_ORDER = list(_AGENT_LABELS.keys())


def _fmt_inr(amount: float | None) -> str:
    if amount is None:
        return "—"
    return f"Rs. {amount:,.0f}".replace(",", ",")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    s = {
        "title":   ParagraphStyle("title",   parent=base["Heading1"], fontSize=20,
                                  textColor=PLUM_MAROON, spaceAfter=2, leading=24),
        "h2":      ParagraphStyle("h2",      parent=base["Heading2"], fontSize=12,
                                  textColor=PLUM_MAROON, spaceBefore=10, spaceAfter=4,
                                  leading=15),
        "body":    ParagraphStyle("body",    parent=base["BodyText"], fontSize=9.5,
                                  textColor=PLUM_DARK, leading=13),
        "meta":    ParagraphStyle("meta",    parent=base["BodyText"], fontSize=9,
                                  textColor=PLUM_GREY, leading=12),
        "cell":    ParagraphStyle("cell",    parent=base["BodyText"], fontSize=8.5,
                                  textColor=PLUM_DARK, leading=11),
        "cellMono":ParagraphStyle("cellMono", parent=base["BodyText"], fontSize=8,
                                  textColor=PLUM_GREY, fontName="Courier", leading=11),
        "verdict": ParagraphStyle("verdict", parent=base["Heading1"], fontSize=22,
                                  textColor=colors.white, alignment=0, leading=26),
    }
    return s


def _decision_question(claim_meta: dict, decision: Decision) -> list[tuple[str, str, str]]:
    """
    The structured Q&A table — each row is (Question, Answer, Reasoning).
    Edge-case-aware: MANUAL_REVIEW with high confidence (e.g. wrong-doc halts) is
    a legitimate well-grounded answer, not an uncertain one.
    """
    rows: list[tuple[str, str, str]] = []
    dtype = decision.decision_type
    amount_breakdown = decision.amount_breakdown

    rows.append((
        "What is the final decision?",
        dtype.value.replace("_", " ").title(),
        decision.explanation or "No explanation recorded.",
    ))

    rows.append((
        "How confident is the system?",
        f"{int(decision.confidence * 100)}%",
        (
            "High confidence — the verdict is strongly supported by the documents and policy rules."
            if decision.confidence >= 0.85
            else "Moderate confidence — minor ambiguity in document or fraud signals."
            if decision.confidence >= 0.6
            else "Low confidence — manual review strongly recommended."
        ),
    ))

    rows.append((
        "What amount was claimed?",
        _fmt_inr(decision.claimed_amount),
        f"Claim category: {claim_meta.get('claim_category', '—')}.",
    ))

    rows.append((
        "What amount was approved?",
        _fmt_inr(decision.approved_amount),
        (
            "Full amount approved."
            if dtype == DecisionType.APPROVED and decision.approved_amount >= decision.claimed_amount
            else "Partial approval after policy deductions."
            if dtype == DecisionType.PARTIAL
            else "No payout — see rejection / review reasons."
            if dtype in (DecisionType.REJECTED, DecisionType.MANUAL_REVIEW)
            else "—"
        ),
    ))

    if decision.rejection_reasons:
        rows.append((
            "Why was the claim not fully approved?",
            ", ".join(r.value for r in decision.rejection_reasons),
            decision.manual_review_note or decision.explanation or "—",
        ))

    if decision.fraud_flags:
        rows.append((
            "Were any fraud signals detected?",
            f"Yes — {len(decision.fraud_flags)} signal(s)",
            "; ".join(decision.fraud_flags),
        ))
    else:
        rows.append((
            "Were any fraud signals detected?",
            "No",
            "No same-day, monthly, alteration, or high-value flags raised.",
        ))

    if decision.component_failures:
        rows.append((
            "Did any pipeline components degrade?",
            f"Yes — {len(decision.component_failures)}",
            "; ".join(decision.component_failures) + ". Pipeline continued with reduced confidence.",
        ))

    if amount_breakdown:
        deductions: list[str] = []
        if amount_breakdown.network_discount_amount > 0:
            deductions.append(
                f"Network discount {amount_breakdown.network_discount_percent:.0f}% "
                f"(-{_fmt_inr(amount_breakdown.network_discount_amount)})"
            )
        if amount_breakdown.copay_amount > 0:
            deductions.append(
                f"Co-pay {amount_breakdown.copay_percent:.0f}% "
                f"(-{_fmt_inr(amount_breakdown.copay_amount)})"
            )
        if amount_breakdown.sub_limit_applied is not None:
            deductions.append(f"Sub-limit capped at {_fmt_inr(amount_breakdown.sub_limit_applied)}")
        if amount_breakdown.per_claim_limit_applied is not None:
            deductions.append(f"Per-claim limit capped at {_fmt_inr(amount_breakdown.per_claim_limit_applied)}")
        rows.append((
            "How was the approved amount calculated?",
            _fmt_inr(amount_breakdown.final_approved),
            " · ".join(deductions) if deductions else "No deductions applied — full claimed amount approved.",
        ))

    return rows


def _color_row(rgb: colors.Color, alpha_bg: float = 0.10) -> colors.Color:
    """Create a low-alpha version of a brand colour for cell backgrounds."""
    r, g, b = rgb.red, rgb.green, rgb.blue
    return colors.Color(r, g, b, alpha=alpha_bg)


def build_pdf(claim_meta: dict, decision: Decision,
              documents: list[dict], trace: list[TraceEvent],
              processing_ms: int) -> bytes:
    """
    Build a PDF report and return the bytes.

    claim_meta keys used: claim_id, member_id, policy_id, claim_category,
                         treatment_date, processing_time_ms, pipeline_complete,
                         degraded_components
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=14 * mm,  bottomMargin=14 * mm,
        title=f"Plum Claim Report — {claim_meta.get('claim_id', '')[:8]}",
        author="Plum Claims Engine",
    )
    s = _styles()
    story = []

    # ── Header ──────────────────────────────────────────────────────────────
    verdict_color = _decision_color = _DECISION_COLOR.get(decision.decision_type, PLUM_GREY)
    verdict_text = decision.decision_type.value.replace("_", " ").title()

    header = Table(
        [[
            Paragraph(f"<b>{verdict_text}</b>", s["verdict"]),
            Paragraph(
                f"<font color='#ffffff' size='10'>Approved</font><br/>"
                f"<font color='#ffffff' size='16'><b>{_fmt_inr(decision.approved_amount)}</b></font><br/>"
                f"<font color='#ffffff' size='8'>of {_fmt_inr(decision.claimed_amount)} claimed</font>",
                s["body"],
            ),
        ]],
        colWidths=[110 * mm, 60 * mm],
    )
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), verdict_color),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    story.append(header)
    story.append(Spacer(1, 6))

    # Sub-header with the title + generated timestamp
    story.append(Paragraph("Plum Claims Engine — Claim Report", s["title"]))
    story.append(Paragraph(
        f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} · "
        f"processed in {processing_ms / 1000:.2f}s · "
        f"{len(trace)} trace events",
        s["meta"],
    ))

    # ── LLM-synthesised narrative ───────────────────────────────────────────
    if decision.narrative:
        story.append(Paragraph("Summary", s["h2"]))
        story.append(Paragraph(decision.narrative, s["body"]))

    # ── Next best actions ───────────────────────────────────────────────────
    if decision.next_best_actions:
        story.append(Paragraph("Next Best Actions", s["h2"]))
        for i, action in enumerate(decision.next_best_actions, 1):
            story.append(Paragraph(f"<b>{i}.</b> {action}", s["body"]))

    # ── Confidence reasoning ────────────────────────────────────────────────
    if decision.confidence_reasoning:
        story.append(Paragraph("Why This Confidence Level", s["h2"]))
        story.append(Paragraph(decision.confidence_reasoning, s["body"]))

    # ── Claim metadata ──────────────────────────────────────────────────────
    story.append(Paragraph("Claim Details", s["h2"]))
    meta_rows = [
        ["Claim ID",        claim_meta.get("claim_id", "—")],
        ["Member",          claim_meta.get("member_id", "—")],
        ["Policy",          claim_meta.get("policy_id", "—")],
        ["Category",        claim_meta.get("claim_category", "—")],
        ["Treatment date",  str(claim_meta.get("treatment_date", "—"))],
        ["Claimed amount",  _fmt_inr(decision.claimed_amount)],
        ["Approved amount", _fmt_inr(decision.approved_amount)],
        ["Confidence",      f"{int(decision.confidence * 100)}%"],
    ]
    meta_table = Table(meta_rows, colWidths=[40 * mm, 130 * mm])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), PLUM_MAROON),
        ("TEXTCOLOR", (1, 0), (1, -1), PLUM_DARK),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [PLUM_OFFWHITE, colors.white]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, PLUM_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(meta_table)

    # ── Decision Q&A table ──────────────────────────────────────────────────
    story.append(Paragraph("Decision Reasoning", s["h2"]))
    qa_rows = [[
        Paragraph("<b>Question</b>", s["cell"]),
        Paragraph("<b>Answer</b>",   s["cell"]),
        Paragraph("<b>Reasoning</b>", s["cell"]),
    ]]
    for q, a, r in _decision_question(claim_meta, decision):
        qa_rows.append([
            Paragraph(q, s["cell"]),
            Paragraph(a, s["cell"]),
            Paragraph(r, s["cell"]),
        ])
    qa_table = Table(qa_rows, colWidths=[55 * mm, 35 * mm, 80 * mm], repeatRows=1)
    qa_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PLUM_MAROON),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [PLUM_OFFWHITE, colors.white]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, PLUM_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(qa_table)

    # ── Amount breakdown ────────────────────────────────────────────────────
    bd = decision.amount_breakdown
    if bd:
        story.append(Paragraph("Amount Breakdown", s["h2"]))
        bd_rows = [["Component", "Value"]]
        bd_rows.append(["Claimed", _fmt_inr(bd.claimed)])
        if bd.network_discount_amount > 0:
            bd_rows.append([
                f"Network discount ({bd.network_discount_percent:.0f}%)",
                f"-{_fmt_inr(bd.network_discount_amount)}",
            ])
            bd_rows.append(["After network discount", _fmt_inr(bd.after_network_discount)])
        if bd.copay_amount > 0:
            bd_rows.append([
                f"Co-pay ({bd.copay_percent:.0f}%)",
                f"-{_fmt_inr(bd.copay_amount)}",
            ])
        if bd.sub_limit_applied is not None:
            bd_rows.append(["Sub-limit applied", _fmt_inr(bd.sub_limit_applied)])
        if bd.per_claim_limit_applied is not None:
            bd_rows.append(["Per-claim limit", _fmt_inr(bd.per_claim_limit_applied)])
        bd_rows.append(["Final approved", _fmt_inr(bd.final_approved)])

        bd_table = Table(bd_rows, colWidths=[110 * mm, 60 * mm])
        bd_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PLUM_MAROON),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [PLUM_OFFWHITE, colors.white]),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, PLUM_BORDER),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("TEXTCOLOR", (1, -1), (1, -1), PLUM_GREEN),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(bd_table)

    # ── Documents processed ─────────────────────────────────────────────────
    if documents:
        story.append(Paragraph("Documents Processed", s["h2"]))
        doc_rows = [["#", "File", "Detected type", "Quality"]]
        for i, d in enumerate(documents, 1):
            doc_rows.append([
                str(i),
                Paragraph(str(d.get("file_name", "—")), s["cell"]),
                str(d.get("doc_type", "—")),
                str(d.get("quality", "GOOD")),
            ])
        doc_table = Table(doc_rows, colWidths=[10 * mm, 80 * mm, 50 * mm, 30 * mm],
                          repeatRows=1)
        doc_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PLUM_MAROON),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [PLUM_OFFWHITE, colors.white]),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, PLUM_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(doc_table)

    # ── Cross-document consistency ──────────────────────────────────────────
    if decision.consistency_flags:
        story.append(Paragraph("Cross-Document Consistency", s["h2"]))
        for f in decision.consistency_flags:
            story.append(Paragraph(f"• {f}", s["body"]))

    # ── Fraud signals ───────────────────────────────────────────────────────
    if decision.fraud_flags:
        story.append(Paragraph("Fraud Signals", s["h2"]))
        for f in decision.fraud_flags:
            story.append(Paragraph(f"• {f}", s["body"]))

    # ── Trace summary ───────────────────────────────────────────────────────
    if trace:
        story.append(Paragraph("Pipeline Trace", s["h2"]))
        by_agent: dict[str, list[TraceEvent]] = {}
        for e in trace:
            by_agent.setdefault(e.agent, []).append(e)

        trace_rows = [["Agent", "Events", "Outcome", "Total ms"]]
        for agent in _AGENT_ORDER:
            evs = by_agent.get(agent, [])
            if not evs:
                continue
            statuses = {ev.status.value for ev in evs}
            outcome = (
                "FAIL" if "FAIL" in statuses
                else "WARN" if "WARN" in statuses
                else "PASS"
            )
            total_ms = sum(ev.duration_ms or 0 for ev in evs)
            trace_rows.append([
                _AGENT_LABELS.get(agent, agent),
                str(len(evs)),
                outcome,
                f"{total_ms} ms" if total_ms else "—",
            ])

        trace_table = Table(trace_rows, colWidths=[55 * mm, 25 * mm, 30 * mm, 30 * mm],
                            repeatRows=1)
        trace_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PLUM_MAROON),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [PLUM_OFFWHITE, colors.white]),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, PLUM_BORDER),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(trace_table)

    # ── Footer ──────────────────────────────────────────────────────────────
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Demo report · Not affiliated with Plum Benefits Insurance Brokers Pvt Ltd.",
        s["meta"],
    ))

    doc.build(story)
    return buf.getvalue()
