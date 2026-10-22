"""Roda uma vez, no seu computador, para autorizar a secretária a usar seu Google Agenda.

Uso:
    pip install google-auth-oauthlib
    python scripts/obter_token_google.py caminho/para/client_secret.json

Abre o navegador, você faz login com a conta Google da agenda, e o script imprime
GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET e GOOGLE_REFRESH_TOKEN para colocar no .env.
"""
import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    path = sys.argv[1]
    flow = InstalledAppFlow.from_client_secrets_file(path, SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    info = json.load(open(path))
    info = info.get("installed") or info.get("web")
    print("\nCopie para o seu .env:\n")
    print(f"GOOGLE_CLIENT_ID={info['client_id']}")
    print(f"GOOGLE_CLIENT_SECRET={info['client_secret']}")
    print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")


if __name__ == "__main__":
    main()
