# CMEMS Fallback & CI/CD Enhancements

## Übersicht

Dieses Dokument beschreibt die neu implementierten Verbesserungen für höhere Ausfallsicherheit und automatisierte Qualitätssicherung.

## 1. CMEMS-Fallback-Logik ✅

### Implementierung

**Datei**: `src/spvx/sea_state/fallback.py`

Die neue `SeaStateFallbackChain` Klasse implementiert eine automatische Fallback-Kette für sea-state Datenquellen:

```
CMEMS (primär) → RTOFS (fallback) → Graceful Degradation (letzte Option)
```

### Features

#### Automatischer Provider-Wechsel
- Versucht zuerst CMEMS (wenn Credentials verfügbar)
- Fällt automatisch auf RTOFS zurück bei CMEMS-Fehler
- Aktiviert Degradation-Modus wenn beide Provider fehlschlagen

#### Fehlerbehandlung
- Detailliertes Logging für jeden Provider-Versuch
- Graceful Handling von Teil-Fehlern (z.B. nur Currents fehlschlagen)
- Strukturierte Ergebnis-Rückgabe mit Status und Fehlerdetails

#### Metriken-Integration
- Prometheus-Metriken für aktiven Provider
- Tracking von Downloads und verarbeiteten Zeilen
- Provider-Status-Updates

### Verwendung

#### CLI-Integration

```bash
# Automatischer Fallback (empfohlen für Production)
python -m spvx.cli ingest-sea-state --provider auto --lookback-days 3

# Spezifischer Provider (für Testing)
python -m spvx.cli ingest-sea-state --provider cmems --lookback-days 3
python -m spvx.cli ingest-sea-state --provider rtofs
```

#### Programmatische Verwendung

```python
from spvx.sea_state.fallback import SeaStateFallbackChain
from spvx.config import load_config

chain = SeaStateFallbackChain(
    cmems_username="your_username",  # pragma: allowlist secret
    cmems_password="your_password",  # pragma: allowlist secret
    config=load_config()
)

result = chain.ingest_with_fallback(lookback_days=3)

if result.status == "success":
    print(f"✓ {result.provider.upper()}: {result.files_downloaded} files")
elif result.status == "degraded":
    print(f"⚠ Degraded mode: {result.error}")
```

## 2. Wetterbasierte Degradationsmasken ✅

### Funktionsweise

Wenn alle Provider fehlschlagen, wird automatisch eine Degradationsmaske erstellt:

**Datei**: `data/processed/weather_degradation_mask.json`

```json
{
  "SEA_HS_Z": true,
  "OPPOSING_CURRENT": true,
  "weather_data_available": false
}
```

### Index-Berechnung mit Degradation

Die Index-Berechnung (`src/spvx/index/spvx_lite.py`) prüft automatisch auf Degradation:

```python
from spvx.sea_state.fallback import should_use_degraded_index

degraded_mode = should_use_degraded_index()

if degraded_mode:
    # Verwendet nur SPVX_LITE_EX_WEATHER (ohne Wetter-Komponenten)
    # Weather-Features werden übersprungen
    print("⚠ Index computation in degraded mode")
```

### Benefits

1. **Keine Pipeline-Unterbrechung**: System läuft weiter, auch ohne Wetterdaten
2. **Transparenz**: Degradation-Status ist klar dokumentiert
3. **Automatische Recovery**: Beim nächsten erfolgreichen Ingest wird Maske entfernt
4. **Metriken**: Degradation-Status ist in Prometheus sichtbar

## 3. CI/CD Pipeline ✅

### GitHub Actions Workflow

**Datei**: `.github/workflows/ci.yml`

#### Pipeline-Struktur

```
┌─────────────┐
│   Lint      │  Ruff, Black, isort
└─────┬───────┘
      │
┌─────▼───────┐
│   Test      │  pytest auf Python 3.10, 3.11, 3.12
└─────┬───────┘
      │
┌─────▼───────┐
│  Security   │  Bandit, Safety
└─────┬───────┘
      │
┌─────▼───────┐
│ Type Check  │  MyPy
└─────┬───────┘
      │
┌─────▼───────┐
│ Integration │  Mock data + Index
└─────┬───────┘
      │
┌─────▼───────┐
│  Release    │  Checklist validation (nur main)
└─────────────┘
```

#### Jobs im Detail

**1. Lint & Format Check**
- Ruff: Fast Python linter
- Black: Code formatter
- isort: Import sorting

**2. Test Suite**
- Matrix: Python 3.10, 3.11, 3.12
- Coverage reporting (Codecov)
- Parallele Ausführung

**3. Security Scan**
- Safety: Dependency vulnerabilities
- Bandit: Security linting

**4. Type Checking**
- MyPy static type analysis
- Pandas stubs included

**5. Integration Tests**
- Mock data ingestion
- Index computation
- Output validation

**6. Release Validation**
- Nur auf `main` branch
- Bestätigt alle Checks erfolgreich

### Lokale Entwicklung

#### Pre-Commit Hooks

**Datei**: `.pre-commit-config.yaml`

Installation:
```bash
pip install pre-commit
pre-commit install
```

Läuft automatisch vor jedem Commit:
- Trailing whitespace removal
- End-of-file fixing
- YAML/JSON validation
- Black formatting
- isort import sorting
- Ruff linting
- Bandit security check
- Quick pytest run

#### Makefile-Befehle

```bash
# Entwicklung
make lint              # Alle Linter
make format            # Code formatieren
make test              # Tests
make test-cov          # Mit Coverage
make type-check        # MyPy
make security          # Security Checks

# CI-Simulation
make ci-check          # Alle Checks lokal

# Cleanup
make clean             # Cache entfernen
```

### Tool-Konfiguration

**pyproject.toml** enthält alle Konfigurationen:

```toml
[tool.ruff]
line-length = 120
select = ["E", "F", "I", "N", "W", "UP", "B", "A"]

[tool.black]
line-length = 120
target-version = ["py310", "py311", "py312"]

[tool.pytest.ini_options]
addopts = "--cov=src --cov-report=term-missing"
markers = ["slow", "integration"]

[tool.mypy]
ignore_missing_imports = true
```

## Monitoring & Metriken

### Prometheus-Metriken

```python
# Provider-Status
spvx_sea_state_provider{source="cmems"} = 1  # aktiv
spvx_sea_state_provider{source="rtofs"} = 0  # inaktiv

# Download-Metriken
spvx_sea_state_files_downloaded_total{provider="cmems", data_type="waves"}

# Freshness
spvx_sea_state_freshness_seconds{chokepoint="CQ_SG"}
```

### CI-Metriken

- Test Coverage: Ziel >80%
- Pipeline-Laufzeit: ~5-8 Minuten
- Security: 0 high/critical issues

## Release-Workflow

### Pre-Release Checklist

1. **Lokale Checks**
   ```bash
   make ci-check
   ```

2. **GitHub Actions**
   - Alle Jobs grün ✅
   - Security-Scan ohne kritische Issues

3. **Funktions-Tests**
   - CMEMS-Provider funktioniert
   - Fallback-Kette getestet
   - Degradation-Maske funktioniert

4. **Release erstellen**
   ```bash
   git tag v0.2.0
   git push --tags
   ```

### Continuous Integration

**Trigger:**
- Push auf `main`, `develop`
- Pull Requests
- Manuell via `workflow_dispatch`

**Branch Protection:**
- Alle CI-Checks müssen bestehen
- Mindestens 1 Review erforderlich
- Aktueller Branch erforderlich

## Troubleshooting

### Fallback-Probleme

**Problem**: Fallback aktiviert sich nicht
```bash
# Logs prüfen
python -m spvx.cli ingest-sea-state --provider auto 2>&1 | grep -i fallback

# CMEMS-Credentials prüfen
echo $CMEMS_USERNAME
```

**Problem**: Degradation-Maske bleibt aktiv
```bash
# Maske entfernen
rm data/processed/weather_degradation_mask.json

# Erneut versuchen
python -m spvx.cli ingest-sea-state --provider auto
```

### CI-Probleme

**Problem**: Linting fehlschlägt
```bash
# Auto-fix
make format

# Check
make lint
```

**Problem**: Tests fehlschlagen lokal aber nicht in CI
```bash
# Environment bereinigen
make clean
pip install -e ".[dev]" --force-reinstall

# Erneut testen
make test
```

**Problem**: Pre-commit Hook zu langsam
```bash
# Hook aktualisieren
pre-commit autoupdate

# Einzelne Hooks überspringen (Notfall)
SKIP=pytest-quick git commit -m "message"
```

## Best Practices

### Fallback-Nutzung

1. **Production**: Immer `--provider auto` verwenden
2. **Testing**: Spezifische Provider für gezielte Tests
3. **Monitoring**: Prometheus-Alerts für Degradation setzen
4. **Recovery**: Automatische Re-Tries bei temporären Fehlern

### CI/CD

1. **Kleine Commits**: Schnellere Pre-commit Hooks
2. **Feature Branches**: `feature/xyz` → PR → `develop` → `main`
3. **Test-First**: Tests vor Implementation schreiben
4. **Security**: Regelmäßig Dependencies aktualisieren

### Code Quality

1. **Coverage**: Nicht unter 80% fallen lassen
2. **Type Hints**: Wo sinnvoll hinzufügen
3. **Docstrings**: Für public APIs erforderlich
4. **Logging**: Strukturiertes Logging verwenden

## Nächste Schritte

### Empfohlene Erweiterungen

1. **Slack/Discord Notifications**
   - CI-Failure Benachrichtigungen
   - Deployment-Updates

2. **Staging Environment**
   - Automatisches Deployment nach `develop`
   - Integration-Tests gegen echte APIs

3. **Performance Monitoring**
   - Pipeline-Laufzeit Tracking
   - Provider-Response-Time Metriken

4. **Automatische Dependency Updates**
   - Dependabot/Renovate Integration
   - Wöchentliche Security-Updates

## Support

- **Dokumentation**: `/docs/CI_SETUP.md`
- **Issues**: GitHub Issues
- **CI-Logs**: GitHub Actions Tab
- **Metriken**: Prometheus/Grafana Dashboard

---

**Implementation Status**: ✅ Vollständig implementiert
**Letzte Aktualisierung**: 2025-10-17
**Version**: 0.2.0
