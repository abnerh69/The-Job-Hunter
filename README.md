# Job Hunter EU 🚀

![CI](https://github.com/v-sh-org/job-hunter-eu/actions/workflows/ci.yml/badge.svg)

Automated job search system for Europe. Designed to help engineers find their next role with less manual effort and more data-driven decisions.

## 🎯 Why this exists

Searching for a job in Europe's diverse market can be overwhelming. Job Hunter EU automates the tedious parts of the job search:
- Scraping and aggregating job offers from multiple sources.
- Scoring jobs based on your preferences and profile.
- Tracking applications and follow-ups.
- Providing a consolidated dashboard of your job search progress.

## 🛠️ Tech Stack

- **Language:** Python 3.12+
- **Environment Management:** [uv](https://github.com/astral-sh/uv)
- **Database:** PostgreSQL with [SQLAlchemy](https://www.sqlalchemy.org/) & [Alembic](https://alembic.sqlalchemy.org/)
- **AI/LLM:** [Anthropic API](https://www.anthropic.com/) (for scoring and parsing)
- **Quality:** [Ruff](https://github.com/astral-sh/ruff), [MyPy](https://mypy-lang.org/), [Pytest](https://docs.pytest.org/)
- **Containerization:** Docker & Docker Compose

## 📋 Prerequisites

- [Docker](https://www.docker.com/) & [Docker Compose](https://docs.docker.com/compose/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (recommended for local development)
- An Anthropic API Key (for job scoring features)

## ⚡ Quick Start (5 min)

Get up and running in 5 commands:

```bash
# 1. Clone and enter the repository
git clone https://github.com/v-sh-org/job-hunter-eu.git && cd job-hunter-eu

# 2. Setup environment variables
cp .env.example .env

# 3. Start the infrastructure
docker compose up -d

# 4. Install dependencies locally (requires uv)
uv sync

# 5. Run tests to verify setup
uv run pytest
```

## 🏗️ Project Structure

The project follows a domain-driven structure. See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for more details.

```text
├── src/jobhunter/
│   ├── db/          # Database models and migrations
│   ├── sources/     # Job board scrapers/APIs
│   ├── scoring/     # LLM-based job scoring
│   ├── application/ # Application tracking
│   ├── notify/      # Notification system
│   └── outreach/    # Automated contact
├── tests/           # Unit and integration tests
├── alembic/         # DB migrations
└── docs/            # Additional documentation
```

## 💻 Development Workflow

1. **Install hooks:** `uv run pre-commit install`
2. **Database Migrations:** `uv run alembic upgrade head`
3. **Run Linting:** `uv run ruff check .`
4. **Run Type Checks:** `uv run mypy .`
5. **Run Tests:** `uv run pytest`

## ⚖️ License

Proprietary - See [LICENSE](LICENSE) (if applicable) or contact the Job Hunter EU Team.
