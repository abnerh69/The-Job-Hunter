# Contributing to Job Hunter EU

First off, thanks for taking the time to contribute! 🎉

The following is a set of guidelines for contributing to Job Hunter EU. These are mostly guidelines, not rules. Use your best judgment, and feel free to propose changes to this document in a pull request.

## Branching Strategy

We use a simplified version of GitFlow:

- `main`: The stable branch. Contains the latest released version.
- `feature/*`: For new features or enhancements.
- `bugfix/*`: For bug fixes.
- `hotfix/*`: For urgent fixes in `main`.

**Workflow:**
1. Create a new branch from `main`.
2. Commit your changes (see Conventional Commits).
3. Open a Pull Request (PR) against `main`.

## Conventional Commits

We follow the [Conventional Commits](https://www.conventionalcommits.org/) specification for commit messages:

- `feat`: A new feature
- `fix`: A bug fix
- `docs`: Documentation only changes
- `style`: Changes that do not affect the meaning of the code (white-space, formatting, etc)
- `refactor`: A code change that neither fixes a bug nor adds a feature
- `perf`: A code change that improves performance
- `test`: Adding missing tests or correcting existing tests
- `chore`: Changes to the build process or auxiliary tools and libraries

**Example:**
```bash
feat(scoring): add new heuristic for remote-only jobs
```

## Pull Request Checklist

Before submitting a PR, please ensure:

- [ ] Your code follows the project's style (run `uv run ruff format .`).
- [ ] Linters pass (run `uv run ruff check .`).
- [ ] Type checks pass (run `uv run mypy .`).
- [ ] All tests pass (run `uv run pytest`).
- [ ] Documentation is updated if necessary.
- [ ] The PR has a descriptive title and description.

## Development Environment

Refer to the [README.md](./README.md) for instructions on setting up your local development environment.
