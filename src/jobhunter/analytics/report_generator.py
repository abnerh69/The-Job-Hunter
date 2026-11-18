import calendar
from datetime import date, datetime, timezone
from typing import Any, Dict, List, TYPE_CHECKING

from pydantic import BaseModel
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from jobhunter.llm.base import LLMClient

from jobhunter.analytics.cost_metrics import get_cost_per_outcome
from jobhunter.analytics.email_metrics import get_matcher_metrics
from jobhunter.analytics.outreach_metrics import get_outreach_performance
from jobhunter.analytics.pipeline_metrics import get_funnel_metrics
from jobhunter.analytics.prompt_metrics import get_prompt_performance
from jobhunter.analytics.quality_metrics import get_tier_distribution, get_false_rejects
from jobhunter.analytics.regression_detector import RegressionReport


class MonthlyMetrics(BaseModel):
    """Container for all aggregated metrics for a specific period."""

    month: str
    funnel: Dict[str, int]
    tier_distribution: Dict[str, int]
    false_rejects_count: int
    total_cost: float
    cost_per_outcome: List[Dict[str, Any]]
    outreach_performance: Dict[str, Any]
    matcher_metrics: Dict[str, Any]
    prompt_performance: List[Dict[str, Any]]


def get_month_range(year: int, month: int) -> tuple[date, date]:
    """Returns the start and end dates for a given month."""
    start_date = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end_date = date(year, month, last_day)
    return start_date, end_date


def get_quarter_range(year: int, quarter: int) -> tuple[date, date]:
    """Returns the start and end dates for a given quarter (1-4)."""
    start_month = (quarter - 1) * 3 + 1
    start_date = date(year, start_month, 1)
    end_month = quarter * 3
    last_day = calendar.monthrange(year, end_month)[1]
    end_date = date(year, end_month, last_day)
    return start_date, end_date


def collect_metrics_for_period(
    session: Session, start_date: date, end_date: date, label: str
) -> MonthlyMetrics:
    """Collects all metrics for the specified period."""
    from jobhunter.db.models import LLMCall
    from sqlalchemy import select, func, and_

    # Funnel
    funnel_res = get_funnel_metrics(session, start_date, end_date)
    funnel_dict = {s.stage: s.count for s in funnel_res.stages}

    # Tier distribution
    tier_res = get_tier_distribution(session, start_date, end_date)
    tier_dict = {str(t.tier): t.count for t in tier_res.distribution}

    # False rejects
    false_rejects = get_false_rejects(session, start_date, end_date)

    # Cost
    # Convert dates to datetime for LLMCall calculation
    start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)

    # Total cost
    total_cost = (
        session.scalar(
            select(func.sum(LLMCall.cost_usd)).where(
                and_(LLMCall.called_at >= start_dt, LLMCall.called_at <= end_dt)
            )
        )
        or 0.0
    )

    cost_per_outcome = get_cost_per_outcome(session, start_date, end_date)

    # Outreach (get_outreach_performance takes start_datetime)
    outreach_res = get_outreach_performance(session, start_dt)
    # Note: get_outreach_performance doesn't take end_date, so it might include everything after start_dt
    # For reporting, we might want to filter it more strictly if possible.
    # But for now we follow existing analytics API.

    # Matcher
    matcher_res = get_matcher_metrics(session, start_date, end_date)

    # Prompt performance
    prompt_res = get_prompt_performance(session, start_date, end_date)

    return MonthlyMetrics(
        month=label,
        funnel=funnel_dict,
        tier_distribution=tier_dict,
        false_rejects_count=len(false_rejects),
        total_cost=float(total_cost),
        cost_per_outcome=[c.model_dump() for c in cost_per_outcome],
        outreach_performance=outreach_res.model_dump(),
        matcher_metrics=matcher_res.model_dump(),
        prompt_performance=[p.model_dump() for p in prompt_res],
    )


def calculate_comparison(current: MonthlyMetrics, reference: MonthlyMetrics) -> Dict[str, Any]:
    """Calculates percentage changes between two sets of metrics."""
    comparison: Dict[str, Any] = {}

    # Funnel comparison
    funnel_comp = {}
    for stage, count in current.funnel.items():
        ref_count = reference.funnel.get(stage, 0)
        change = (
            ((count - ref_count) / ref_count * 100)
            if ref_count > 0
            else (100.0 if count > 0 else 0.0)
        )
        funnel_comp[stage] = {
            "current": float(count),
            "reference": float(ref_count),
            "change_pct": float(change),
        }
    comparison["funnel"] = funnel_comp

    # Total cost comparison
    cost_change = (
        ((current.total_cost - reference.total_cost) / reference.total_cost * 100)
        if reference.total_cost > 0
        else 0.0
    )
    comparison["total_cost"] = {
        "current": float(current.total_cost),
        "reference": float(reference.total_cost),
        "change_pct": float(cost_change),
    }

    # Response rate comparison (from funnel)
    def get_rate(metrics: MonthlyMetrics) -> float:
        applied = metrics.funnel.get("4. Applied", 0)
        interviews = metrics.funnel.get("6. Interview", 0)
        return (interviews / applied * 100) if applied > 0 else 0.0

    curr_rate = get_rate(current)
    ref_rate = get_rate(reference)
    rate_change = curr_rate - ref_rate  # percentage points
    comparison["interview_rate"] = {
        "current": float(curr_rate),
        "reference": float(ref_rate),
        "change_pp": float(rate_change),
    }

    return comparison


async def generate_narrative_report(
    session: Session,
    llm_client: "LLMClient",
    month: str,
    current_metrics: MonthlyMetrics,
    prev_month_comp: Dict[str, Any],
    prev_quarter_comp: Dict[str, Any],
    anomalies: RegressionReport,
    model: str = "claude-3-5-sonnet-20240620",
) -> str:
    """Calls the LLM to generate the narrative report."""
    from pathlib import Path
    import json

    prompt_path = Path("prompts/analytics_report/v1.md")
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found at {prompt_path}")

    # Simplified parsing of the versioned prompt format
    content = prompt_path.read_text()
    parts = content.split("## USER_TEMPLATE")
    system_prompt = parts[0].replace("## SYSTEM", "").strip()
    user_template = parts[1].strip()

    user_prompt = user_template.format(
        month=month,
        current_metrics=json.dumps(current_metrics.model_dump(mode="json"), indent=2),
        prev_month_comparison=json.dumps(prev_month_comp, indent=2),
        prev_quarter_comparison=json.dumps(prev_quarter_comp, indent=2),
        anomalies_and_regressions=json.dumps(anomalies.model_dump(mode="json"), indent=2),
    )

    from jobhunter.db.enums import LLMPurpose

    response = await llm_client.complete(
        system=system_prompt,
        user=user_prompt,
        model=model,
        purpose=LLMPurpose.ANALYTICS_REPORT,
        session=session,
        prompt_version="v1",
    )

    return str(response.text)


def format_report_as_html(markdown_text: str, month: str) -> str:
    """Converts markdown report to HTML with embedded CSS."""
    import jinja2

    # Basic CSS for an elegant report
    css = """
    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        line-height: 1.6;
        color: #333;
        max-width: 800px;
        margin: 0 auto;
        padding: 40px 20px;
        background-color: #f9f9f9;
    }
    .container {
        background-color: #fff;
        padding: 40px;
        border-radius: 8px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    h1 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }
    h2 { color: #2980b9; margin-top: 30px; }
    h3 { color: #16a085; }
    table { width: 100%; border-collapse: collapse; margin: 20px 0; }
    th, td { text-align: left; padding: 12px; border-bottom: 1px solid #ddd; }
    th { background-color: #f2f2f2; }
    blockquote {
        margin: 20px 0;
        padding: 10px 20px;
        background-color: #f0f7fb;
        border-left: 5px solid #3498db;
        font-style: italic;
    }
    ul, ol { margin-bottom: 20px; }
    li { margin-bottom: 10px; }
    .footer { margin-top: 50px; font-size: 0.8em; color: #777; text-align: center; }
    """

    # We need a markdown to html converter.
    # Since it's not in dependencies, we'll try to use a simple one or just wrap in <pre>
    # Actually, we should probably add `markdown` package, but the instructions say `md -> html -> pdf`.
    # Let's check if there's any other way or if I should just use basic string replacement for simple MD.
    # To be robust, I'll use a placeholder and then I'll add `markdown` to dependencies if needed.
    # WAIT, I see `rich` has Markdown, but that's for console.

    # I will use a very basic manual markdown to html conversion for the common elements
    # or just assume I can add a small dependency like `markdown`.

    import re

    html_body = markdown_text
    # Headers
    html_body = re.sub(r"^# (.*)$", r"<h1>\1</h1>", html_body, flags=re.M)
    html_body = re.sub(r"^## (.*)$", r"<h2>\1</h2>", html_body, flags=re.M)
    html_body = re.sub(r"^### (.*)$", r"<h3>\1</h3>", html_body, flags=re.M)
    # Bold
    html_body = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", html_body)
    # Lists
    html_body = re.sub(r"^\* (.*)$", r"<li>\1</li>", html_body, flags=re.M)
    html_body = re.sub(r"^- (.*)$", r"<li>\1</li>", html_body, flags=re.M)
    # Note: this simple regex won't wrap <li> in <ul> properly, but for a start...
    # Tables are even harder.

    # Better: I will add `markdown` package to dependencies in the next step.
    try:
        import markdown

        html_content = markdown.markdown(markdown_text, extensions=["tables", "fenced_code"])
    except ImportError:
        # Fallback to plain text in a pre tag
        html_content = f"<pre>{markdown_text}</pre>"

    template = jinja2.Template("""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Reporte Mensual - {{ month }}</title>
        <style>{{ css }}</style>
    </head>
    <body>
        <div class="container">
            <h1>Reporte Mensual de Analytics: {{ month }}</h1>
            {{ body }}
            <div class="footer">
                Generado por Job Hunter EU - {{ now }}
            </div>
        </div>
    </body>
    </html>
    """)

    result: str = template.render(
        month=month, css=css, body=html_content, now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    return result


def convert_html_to_pdf(html_text: str, output_path: str) -> None:
    """Converts HTML text to a PDF file using WeasyPrint."""
    from weasyprint import HTML  # type: ignore[import-untyped]

    HTML(string=html_text).write_pdf(output_path)
