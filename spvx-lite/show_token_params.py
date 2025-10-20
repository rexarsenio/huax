#!/usr/bin/env python3
"""
Zeigt alle Token-Request-Parameter für den NxtPort Support (ohne Secrets)
"""
import os
from dotenv import load_dotenv

load_dotenv()

print("=" * 70)
print("TOKEN REQUEST PARAMETER FÜR NXTPORT SUPPORT")
print("=" * 70)
print()

# Token URL
token_url = os.getenv("NXTPORT_TOKEN_URL", "https://login-uat.nxtport.com/connect/token")
print(f"Token URL:")
print(f"  {token_url}")
print()

# Request Method
print(f"HTTP Method:")
print(f"  POST")
print()

# Headers
print(f"Request Headers:")
print(f"  Content-Type: application/x-www-form-urlencoded")
print()

# Body Parameters
print(f"Request Body Parameters (application/x-www-form-urlencoded):")
print()

grant_type = os.getenv("NXTPORT_GRANT_TYPE", "password")
client_id = os.getenv("NXTPORT_CLIENT_ID")
username = os.getenv("NXTPORT_USERNAME")
scope = os.getenv("NXTPORT_SCOPE", "openid")

print(f"  grant_type = {grant_type}")
print(f"  client_id = {client_id}")
print(f"  client_secret = [REDACTED - vorhanden: {'Ja' if os.getenv('NXTPORT_CLIENT_SECRET') else 'Nein'}]")

if grant_type == "password":
    print(f"  username = {username}")
    print(f"  password = [REDACTED - vorhanden: {'Ja' if os.getenv('NXTPORT_PASSWORD') else 'Nein'}]")

if scope:
    print(f"  scope = {scope}")

print()
print("=" * 70)
print("CURL COMMAND (zum Testen - MIT IHREN SECRETS)")
print("=" * 70)
print()

# Build curl command
client_secret = os.getenv("NXTPORT_CLIENT_SECRET", "")
password = os.getenv("NXTPORT_PASSWORD", "")

curl_data_parts = [
    f"grant_type={grant_type}",
    f"client_id={client_id}",
    f"client_secret={client_secret}",
]

if scope:
    curl_data_parts.append(f"scope={scope}")

if grant_type == "password":
    curl_data_parts.append(f"username={username}")
    curl_data_parts.append(f"password={password}")

curl_data = "&".join(curl_data_parts)

curl_command = f'''curl -v -X POST "{token_url}" \\
  -H "Content-Type: application/x-www-form-urlencoded" \\
  -d "{curl_data}"'''

print(curl_command)
print()

print("=" * 70)
print("FÜR ARXUS PASSWORD SHARING")
print("=" * 70)
print()
print("Teilen Sie folgende Information über https://password.arxus.eu/:")
print()
print(f"Token URL: {token_url}")
print(f"HTTP Method: POST")
print(f"Content-Type: application/x-www-form-urlencoded")
print()
print("Request Body:")
print(f"  grant_type={grant_type}")
print(f"  client_id={client_id}")
print(f"  client_secret={client_secret}")
if scope:
    print(f"  scope={scope}")
if grant_type == "password":
    print(f"  username={username}")
    print(f"  password={password}")
print()
