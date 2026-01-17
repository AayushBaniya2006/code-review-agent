# Contributing to Change-Aware Auditor

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/change-aware-auditor.git`
3. Create a branch: `git checkout -b feature/your-feature-name`
4. Install dependencies: `pip install -r requirements.txt`
5. Make your changes
6. Run tests: `pytest tests/`
7. Submit a pull request

## Development Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install dev dependencies
pip install pytest pytest-cov pytest-asyncio ruff black

# Run the server
uvicorn app.main:app --reload
```

## Code Style

- Follow PEP 8 guidelines
- Use type hints where possible
- Format code with `black`
- Check linting with `ruff`

```bash
# Format code
black app/ tests/

# Check linting
ruff check app/ tests/
```

## Testing

- Write tests for new features
- Ensure all tests pass before submitting PR
- Aim for high test coverage

```bash
# Run tests
pytest tests/

# Run with coverage
pytest --cov=app tests/
```

## Pull Request Guidelines

1. **One feature per PR** - Keep changes focused
2. **Write descriptive commit messages** - Explain what and why
3. **Update documentation** - If your change affects docs
4. **Add tests** - For new features or bug fixes
5. **Follow the template** - Fill out the PR template completely

## Commit Message Format

```
<type>: <short description>

<longer description if needed>

Co-Authored-By: Your Name <your@email.com>
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

## Reporting Issues

When reporting bugs, please include:
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Python version)
- Relevant logs or error messages

## Security Issues

For security vulnerabilities, please email directly rather than opening a public issue.

## Code of Conduct

Be respectful and inclusive. We welcome contributors of all backgrounds and experience levels.

## Questions?

Open an issue with the `question` label or reach out to the maintainers.

---

Thank you for contributing!
