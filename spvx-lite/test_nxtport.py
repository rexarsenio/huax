#!/usr/bin/env python3
"""
NxtPort API Diagnose-Skript
Tests authentication and API access for debugging UAT setup
"""
import os
import sys
import json
from datetime import datetime, timezone
from dotenv import load_dotenv
import requests
import pytest

load_dotenv()


@pytest.fixture(scope="module")
def token():
    """Obtain an OAuth token once per test module."""
    token_value = test_authentication()
    if token_value is None:
        pytest.skip("NXTPort credentials not configured; skipping API diagnostics.")
    return token_value

def test_authentication():
    """Test OAuth2 token retrieval"""
    print("=" * 60)
    print("1. TESTE AUTHENTIFIZIERUNG")
    print("=" * 60)

    token_url = os.getenv("NXTPORT_TOKEN_URL", "https://login-uat.nxtport.com/connect/token")
    client_id = os.getenv("NXTPORT_CLIENT_ID")
    client_secret = os.getenv("NXTPORT_CLIENT_SECRET")
    username = os.getenv("NXTPORT_USERNAME")
    password = os.getenv("NXTPORT_PASSWORD")
    grant_type = os.getenv("NXTPORT_GRANT_TYPE", "password")
    scope = os.getenv("NXTPORT_SCOPE", "openid")

    print(f"Token URL: {token_url}")
    print(f"Client ID: {client_id}")
    print(f"Username: {username}")
    print(f"Grant Type: {grant_type}")
    print(f"Scope: {scope}")
    print()

    if not all([client_id, client_secret]):
        print("❌ FEHLER: CLIENT_ID oder CLIENT_SECRET fehlt in .env")
        return None

    data = {
        "grant_type": grant_type,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    if scope:
        data["scope"] = scope

    if grant_type == "password":
        if not username or not password:
            print("❌ FEHLER: USERNAME oder PASSWORD fehlt für password grant")
            return None
        data["username"] = username
        data["password"] = password

    try:
        print(f"Sende Token-Anfrage an {token_url}...")
        response = requests.post(
            token_url,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "spvx-lite/0.1 (+https://huax.ai)"
            },
            data=data,
            timeout=20
        )

        print(f"Status Code: {response.status_code}")

        if response.status_code != 200:
            print(f"❌ Token-Anfrage fehlgeschlagen!")
            print(f"Response: {response.text}")
            return None

        payload = response.json()
        token = payload.get("access_token")
        expires_in = payload.get("expires_in", 0)

        if not token:
            print("❌ Keine access_token im Response!")
            print(f"Response: {json.dumps(payload, indent=2)}")
            return None

        print(f"✅ Token erfolgreich abgerufen!")
        print(f"   Gültig für: {expires_in} Sekunden ({expires_in/60:.1f} Minuten)")
        print(f"   Token (erste 50 Zeichen): {token[:50]}...")
        print()

        return token

    except requests.exceptions.RequestException as e:
        print(f"❌ Netzwerkfehler: {e}")
        return None


def test_portstays_api(token):
    """Test PortStays API endpoint"""
    print("=" * 60)
    print("2. TESTE PORTSTAYS API")
    print("=" * 60)

    if not token:
        print("⚠️  Überspringe API-Test (kein Token verfügbar)")
        return

    api_base = os.getenv("NXTPORT_API_BASE", "https://api-uat.nxtport.com/portstays/v1")
    subscription_key = os.getenv("NXTPORT_SUBSCRIPTION_KEY")

    print(f"API Base: {api_base}")
    print(f"Subscription Key: {subscription_key[:20]}..." if subscription_key else "Subscription Key: FEHLT!")
    print()

    if not subscription_key:
        print("❌ FEHLER: NXTPORT_SUBSCRIPTION_KEY fehlt in .env")
        return

    # Test mit aktuellem Datum
    now = datetime.now(timezone.utc)
    iso_date = now.isoformat().replace("+00:00", "Z")

    url = f"{api_base}/stays"
    headers = {
        "Authorization": f"Bearer {token}",
        "Ocp-Apim-Subscription-Key": subscription_key,
        "User-Agent": "spvx-lite-portstays/0.1 (+https://huax.ai)"
    }
    params = {"date": iso_date}

    print(f"Anfrage: GET {url}")
    print(f"Parameter: date={iso_date}")
    print()

    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)

        print(f"Status Code: {response.status_code}")
        print(f"Response Headers:")
        for key, value in response.headers.items():
            if key.lower() in ['content-type', 'content-length', 'date', 'x-ratelimit-remaining', 'retry-after']:
                print(f"  {key}: {value}")
        print()

        if response.status_code == 200:
            print("✅ API-Anfrage erfolgreich!")
            try:
                data = response.json()
                print(f"Response-Struktur:")
                print(f"  Typ: {type(data)}")

                if isinstance(data, dict):
                    print(f"  Keys: {list(data.keys())}")
                    if "stays" in data:
                        print(f"  Anzahl Stays: {len(data.get('stays', []))}")
                    if "items" in data:
                        print(f"  Anzahl Items: {len(data.get('items', []))}")
                elif isinstance(data, list):
                    print(f"  Anzahl Einträge: {len(data)}")

                print()
                print(f"Response (erste 500 Zeichen):")
                print(json.dumps(data, indent=2)[:500])
                print("...")

            except json.JSONDecodeError:
                print(f"Response (Text): {response.text[:500]}")

        elif response.status_code == 401:
            print("❌ Authentifizierung fehlgeschlagen (401 Unauthorized)")
            print("Mögliche Ursachen:")
            print("  - Token ist abgelaufen")
            print("  - Ungültige Subscription Key")
            print("  - Fehlende Berechtigungen")
            print(f"Response: {response.text}")

        elif response.status_code == 403:
            print("❌ Zugriff verweigert (403 Forbidden)")
            print("Mögliche Ursachen:")
            print("  - Organisation noch nicht synchronisiert (4-Stunden-Wartezeit!)")
            print("  - Fehlende API-Berechtigungen")
            print("  - Subscription Key nicht aktiviert")
            print(f"Response: {response.text}")

        elif response.status_code == 404:
            print("❌ Endpoint nicht gefunden (404 Not Found)")
            print("Mögliche Ursachen:")
            print("  - Falsche API Base URL")
            print("  - API Version nicht verfügbar")
            print(f"Response: {response.text}")

        elif response.status_code == 429:
            print("❌ Rate Limit überschritten (429 Too Many Requests)")
            print(f"Response: {response.text}")

        else:
            print(f"❌ Unerwarteter Status Code: {response.status_code}")
            print(f"Response: {response.text}")

    except requests.exceptions.RequestException as e:
        print(f"❌ Netzwerkfehler: {e}")


def main():
    print()
    print("NxtPort UAT API Diagnose")
    print("=" * 60)
    print()

    # Schritt 1: Authentifizierung testen
    token = test_authentication()

    # Schritt 2: API-Endpoint testen
    test_portstays_api(token)

    print()
    print("=" * 60)
    print("DIAGNOSE ABGESCHLOSSEN")
    print("=" * 60)
    print()

    if token:
        print("Nächste Schritte:")
        print("1. Wenn API-Status 403: Warten Sie die volle 4-Stunden-Synchronisation ab")
        print("2. Wenn API-Status 200: Integration ist bereit!")
        print("3. Bei anderen Fehlern: Kontaktieren Sie support@nxtport.com")
    else:
        print("Bitte überprüfen Sie Ihre .env Konfiguration und versuchen Sie es erneut.")


if __name__ == "__main__":
    main()
