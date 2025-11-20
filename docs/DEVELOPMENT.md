# Development Guide

This guide covers the development workflow for LiveVTT, including code quality tools, testing, and CI/CD.

## Getting Started

### Prerequisites

- Python 3.10 or higher
- Poetry for dependency management
- Git for version control

### Initial Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd livevtt
   ```

2. **Install dependencies:**
   ```bash
   # Install core dependencies
   poetry install

   # Install with NLLB translation support (optional)
   poetry install -E nllb
   ```

3. **Install pre-commit hooks:**
   ```bash
   poetry run pre-commit install
   ```

## Code Quality Tools

LiveVTT uses several tools to maintain code quality:

### Ruff

Ruff is a fast Python linter and formatter that replaces black, isort, and flake8.

**Run linter:**
```bash
poetry run ruff check src/
```

**Auto-fix issues:**
```bash
poetry run ruff check --fix src/
```

**Format code:**
```bash
poetry run ruff format src/
```

**Configuration:** See `[tool.ruff]` and `[tool.ruff.lint]` in `pyproject.toml`

### Mypy

Mypy provides static type checking.

**Run type checker:**
```bash
poetry run mypy src/python/
```

**Configuration:** See `[tool.mypy]` in `pyproject.toml`

### Bandit

Bandit scans for common security issues.

**Run security scanner:**
```bash
poetry run bandit -r src/python/ -c pyproject.toml
```

**Configuration:** See `[tool.bandit]` in `pyproject.toml`

### Pre-commit Hooks

Pre-commit hooks automatically run checks before each commit.

**Manual run on all files:**
```bash
poetry run pre-commit run --all-files
```

**Update hook versions:**
```bash
poetry run pre-commit autoupdate
```

**Bypass hooks (not recommended):**
```bash
git commit --no-verify
```

## Testing

### Running Tests

**Run all tests:**
```bash
poetry run pytest
```

**Run with coverage:**
```bash
poetry run pytest --cov=src/python --cov-report=term-missing
```

**Run specific test file:**
```bash
poetry run pytest tests/test_archive_transcriber.py
```

**Run with verbose output:**
```bash
poetry run pytest -v
```

### Writing Tests

- Place test files in `tests/` directory
- Name test files `test_*.py` or `*_test.py`
- Name test functions `test_*`
- Use pytest fixtures for setup/teardown
- Aim for high coverage of critical paths

## CI/CD Pipeline

The project uses GitHub Actions for continuous integration and deployment.

### Main CI Workflow

**File:** `.github/workflows/ci.yml`

**Triggers:**
- Push to `main`, `master`, or `develop` branches
- Pull requests to these branches
- Manual workflow dispatch

**Jobs:**

1. **Lint** - Runs ruff linter, formatter, mypy, and bandit
2. **Test** - Runs pytest on Python 3.10, 3.11, 3.12
3. **Pre-commit** - Validates pre-commit hooks
4. **Build** - Tests package build with Poetry

### Translation Tools Workflow

**File:** `.github/workflows/translation-tools.yml`

**Triggers:**
- Changes to `src/python/tools/*translator*.py`
- Changes to the workflow file itself
- Manual workflow dispatch

**Jobs:**
- `test-nllb` - Tests NLLB translator
- `test-libretranslate` - Tests LibreTranslate translator
- `test-mistral` - Tests Mistral translator

Each job performs syntax checks and runs `--help` commands.

## Development Workflow

### Standard Workflow

1. **Create a feature branch:**
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make your changes:**
   ```bash
   # Edit files
   vim src/python/tools/my_tool.py
   ```

3. **Run code quality checks:**
   ```bash
   # Format code
   poetry run ruff format src/

   # Check for issues
   poetry run ruff check src/
   poetry run mypy src/python/
   poetry run bandit -r src/python/ -c pyproject.toml
   ```

4. **Run tests:**
   ```bash
   poetry run pytest --cov=src/python
   ```

5. **Commit changes:**
   ```bash
   git add .
   git commit -m "feat: add my feature"
   # Pre-commit hooks will run automatically
   ```

6. **Push and create PR:**
   ```bash
   git push origin feature/my-feature
   # Create PR on GitHub
   ```

### Pre-commit Hook Failures

If pre-commit hooks fail:

1. **Review the errors:**
   ```bash
   # The output will show what failed and why
   ```

2. **Fix issues automatically (if possible):**
   ```bash
   poetry run ruff check --fix src/
   poetry run ruff format src/
   ```

3. **Fix remaining issues manually:**
   ```bash
   # Edit files to fix mypy or bandit issues
   ```

4. **Try committing again:**
   ```bash
   git add .
   git commit -m "your message"
   ```

## Code Style Guidelines

### Python Style

- **Line length:** 120 characters (configured in ruff)
- **Target version:** Python 3.10+
- **Formatting:** Handled by ruff format
- **Import sorting:** Handled by ruff
- **Type hints:** Use where possible, checked by mypy

### Linting Rules

The project uses ruff with the following rule sets:

- `E` - pycodestyle errors
- `W` - pycodestyle warnings
- `F` - pyflakes
- `I` - isort (import sorting)
- `B` - flake8-bugbear
- `C4` - flake8-comprehensions
- `UP` - pyupgrade
- `ARG` - flake8-unused-arguments
- `SIM` - flake8-simplify

**Ignored rules:**
- `E501` - Line too long (handled by formatter)
- `B008` - Function calls in argument defaults
- `B904` - Raising exceptions without `from e`

### Security

- **Tool:** Bandit scans for security issues
- **Skipped checks:**
  - `B101` - Assert statements (allowed in tests)
  - `B601` - Shell injection (we use subprocess.run with list args)

## Adding Dependencies

### Runtime Dependencies

```bash
poetry add package-name
```

### Development Dependencies

```bash
poetry add --group dev package-name
```

### Optional Dependencies

For optional features like NLLB:

1. **Add to pyproject.toml:**
   ```toml
   [tool.poetry.dependencies]
   new-package = {version = "*", optional = true}

   [tool.poetry.extras]
   feature-name = ["new-package"]
   ```

2. **Install with extras:**
   ```bash
   poetry install -E feature-name
   ```

## Troubleshooting

### Pre-commit hooks not running

```bash
# Reinstall hooks
poetry run pre-commit uninstall
poetry run pre-commit install

# Test manually
poetry run pre-commit run --all-files
```

### Mypy errors on imports

```bash
# Mypy is configured to ignore missing imports
# If you need stubs, install them:
poetry add --group dev types-package-name
```

### Ruff conflicts with existing code

```bash
# Auto-fix what can be fixed
poetry run ruff check --fix src/

# For remaining issues, add to pyproject.toml:
[tool.ruff.lint]
ignore = ["RULE-CODE"]
```

### CI/CD failures

1. Check the GitHub Actions logs for details
2. Reproduce locally using the same commands
3. Fix issues and push again
4. CI runs automatically on push

## Best Practices

1. **Always run pre-commit before pushing:**
   ```bash
   poetry run pre-commit run --all-files
   ```

2. **Write tests for new features:**
   - Add tests in `tests/` directory
   - Maintain high coverage

3. **Keep commits atomic:**
   - One logical change per commit
   - Use conventional commit messages

4. **Update documentation:**
   - Update README.md for user-facing changes
   - Update this guide for dev workflow changes

5. **Review CI/CD results:**
   - Check that all jobs pass
   - Fix failures before merging

## Resources

- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [Mypy Documentation](https://mypy.readthedocs.io/)
- [Bandit Documentation](https://bandit.readthedocs.io/)
- [Pre-commit Documentation](https://pre-commit.com/)
- [Poetry Documentation](https://python-poetry.org/docs/)
- [Pytest Documentation](https://docs.pytest.org/)
