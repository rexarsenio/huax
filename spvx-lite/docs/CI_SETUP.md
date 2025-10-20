# CI/CD Pipeline Setup

## Overview

Das SPVX-Lite Projekt verwendet eine umfassende CI/CD-Pipeline für automatisierte Tests, Linting und Security-Checks.

## GitHub Actions Workflow

Die Pipeline läuft automatisch bei:
- Push auf `main` oder `develop` Branch
- Pull Requests gegen `main` oder `develop`
- Manuellem Trigger via `workflow_dispatch`

### Pipeline-Jobs

#### 1. **Lint & Format Check**
- Ruff (Fast Python linter)
- Black (Code formatter)
- isort (Import sorting)

#### 2. **Test Suite**
- Pytest auf Python 3.10, 3.11, 3.12
- Code Coverage (Codecov Integration)

#### 3. **Security Scan**
- Safety (Dependency vulnerability check)
- Bandit (Security linter)

#### 4. **Type Checking**
- MyPy (Static type checker)

#### 5. **Integration Tests**
- Mock data ingestion
- Index computation
- Output validation

#### 6. **Release Checklist Validation**
- Nur auf `main` Branch
- Validiert dass alle Checks erfolgreich waren

## Lokale Entwicklung

### Installation der Dev-Tools

```bash
# Mit pip
pip install -e ".[dev]"

# Oder mit Make
make install
```

### Pre-Commit Hooks

Pre-commit hooks führen automatische Checks vor jedem Commit durch:

```bash
# Installation
pip install pre-commit
pre-commit install

# Manuell ausführen
pre-commit run --all-files
```

### Makefile-Befehle

```bash
# Linting
make lint              # Alle Linter ausführen
make format            # Code formatieren (black, isort)

# Testing
make test              # Pytest
make test-cov          # Mit Coverage-Report
make test-integration  # Nur Integration-Tests

# Type Checking
make type-check        # MyPy

# Security
make security          # Bandit + Safety

# Alles zusammen
make ci-check          # Alle CI-Checks lokal ausführen

# Cleanup
make clean             # Cache-Dateien entfernen
```

## CI-Pipeline Konfiguration

### Workflow-Datei
`.github/workflows/ci.yml`

### Pytest-Konfiguration
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--verbose --tb=short --strict-markers --cov=src"
markers = [
    "slow: marks tests as slow",
    "integration: marks tests as integration tests",
]
```

### Ruff-Konfiguration
```toml
[tool.ruff]
line-length = 120
target-version = "py310"
select = ["E", "F", "I", "N", "W", "UP", "B", "A"]
ignore = ["E501"]
```

### Black-Konfiguration
```toml
[tool.black]
line-length = 120
target-version = ["py310", "py311", "py312"]
```

## Release-Workflow

Vor jedem Release muss die CI-Pipeline erfolgreich durchlaufen:

1. **Pre-Release Checks**
   ```bash
   make ci-check
   ```

2. **Manuelle Checks** (siehe Checklist im Projekt)
   - CMEMS sea-state provider funktioniert
   - Fallback-Logik getestet
   - Degradation-Maske funktioniert
   - Integration-Tests erfolgreich

3. **GitHub Actions Status**
   - Alle Jobs müssen ✅ grün sein
   - Security-Scan ohne kritische Issues

4. **Release erstellen**
   - Tag erstellen: `v0.1.0`
   - Release Notes schreiben
   - Deployment durchführen

## Monitoring & Metriken

### CI-Metriken
- Test Coverage: Ziel >80%
- Code Quality: Ruff Score
- Security: 0 high/critical vulnerabilities

### Pipeline-Performance
- Durchschnittliche Laufzeit: ~5-8 Minuten
- Parallele Job-Ausführung für Geschwindigkeit

## Troubleshooting

### Häufige Probleme

**Linting-Fehler**
```bash
# Auto-fix mit
make format
```

**Test-Fehler**
```bash
# Detaillierte Ausgabe
pytest -vv --tb=long
```

**Pre-Commit Hook schlägt fehl**
```bash
# Hooks aktualisieren
pre-commit autoupdate

# Hook überspringen (nur in Notfällen!)
git commit --no-verify
```

**Security-Issues**
```bash
# Safety-Report anzeigen
safety check --full-report

# Bandit-Report
bandit -r src -f json | jq
```

## Erweiterte Konfiguration

### Codecov Integration

Fügen Sie in GitHub Repository Settings ein Codecov-Token hinzu:
- Settings → Secrets → `CODECOV_TOKEN`

### Slack/Discord Benachrichtigungen

Workflow erweitern für Notifications:
```yaml
- name: Notify on failure
  if: failure()
  uses: 8398a7/action-slack@v3
  with:
    status: ${{ job.status }}
```

## Beste Praktiken

1. **Kleine, fokussierte Commits**
   - Pre-commit hooks laufen schneller
   - Einfachere Code-Reviews

2. **Tests vor Push**
   ```bash
   make ci-check
   ```

3. **Feature Branches**
   - `feature/xyz` → PR → `develop` → `main`

4. **Security First**
   - Regelmäßig `safety check` ausführen
   - Dependencies aktuell halten

5. **Code Coverage**
   - Neue Features mit Tests abdecken
   - Coverage nicht unter 80% fallen lassen

## Support

Bei Fragen zur CI-Pipeline:
- GitHub Issues: [Link zum Repository]
- Dokumentation: Siehe `/docs`
- Slack: #spvx-lite-dev (falls vorhanden)
