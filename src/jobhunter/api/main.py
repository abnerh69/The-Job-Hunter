from typing import Dict
from fastapi import FastAPI, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi.responses import HTMLResponse
from jobhunter.db.session import get_session
from jobhunter.config import Settings
from jobhunter.health import get_health_report, HealthReport
from jobhunter.db.enums import JobTier
from datetime import datetime, timedelta, timezone

app = FastAPI(title="Job Hunter EU API Sidecar")


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


@app.get("/health", response_model=HealthReport)
def health(
    response: Response,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> HealthReport:
    report = get_health_report(session, settings)
    if report.status == "unhealthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    import structlog

    logger = structlog.get_logger(__name__)
    if response.status_code == 503:
        logger.warning("health_check_failed", report=report.model_dump())

    return report


@app.get("/readiness")
def readiness(response: Response, session: Session = Depends(get_session)) -> Dict[str, str]:
    # ¿DB conectable? ¿Migrations al día? ¿Secrets cargados? ¿Servicios externos accesibles?
    # Readiness focus on critical infrastructure.
    from sqlalchemy import text

    try:
        session.execute(text("SELECT 1")).scalar()
        # Check migrations
        current_rev = session.execute(text("SELECT version_num FROM alembic_version")).scalar()
        if not current_rev:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": "unready", "reason": "No migrations found"}
    except Exception as e:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unready", "reason": str(e)}

    return {"status": "ready"}


@app.get("/status", response_class=HTMLResponse)
def public_status(
    session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
) -> HTMLResponse:
    report = get_health_report(session, settings)

    # Sanitization: Fetch public safe totals
    total_jobs = session.execute(text("SELECT COUNT(*) FROM jobs")).scalar()

    one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    tier_a_last_week = session.execute(
        text("SELECT COUNT(*) FROM jobs WHERE tier = :tier AND scraped_at >= :since"),
        {"tier": JobTier.A.value, "since": one_week_ago},
    ).scalar()

    html_content = f"""
    <html>
        <head>
            <title>System Status - Job Hunter EU</title>
            <style>
                body {{ font-family: sans-serif; margin: 40px; line-height: 1.6; }}
                .status-indicator {{
                    display: inline-block;
                    width: 20px;
                    height: 20px;
                    border-radius: 50%;
                    margin-right: 10px;
                }}
                .healthy {{ background-color: green; }}
                .degraded {{ background-color: orange; }}
                .unhealthy {{ background-color: red; }}
                .card {{
                    border: 1px solid #ddd;
                    padding: 20px;
                    border-radius: 8px;
                    max-width: 600px;
                }}
            </style>
        </head>
        <body>
            <h1>Job Hunter EU System Status</h1>
            <div class="card">
                <p>
                    <span class="status-indicator {report.status}"></span>
                    Current Status: <strong>{report.status.upper()}</strong>
                </p>
                <p>Last Pipeline Run: {report.metrics.last_pipeline_run_at}</p>
                <hr>
                <h3>Public Stats</h3>
                <ul>
                    <li>Total Jobs Processed: {total_jobs}</li>
                    <li>Tier-A Matches (Last 7 days): {tier_a_last_week}</li>
                </ul>
            </div>
            <p><small>Uptime monitoring provided by internal health checks.</small></p>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)
