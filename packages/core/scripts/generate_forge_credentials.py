#!/usr/bin/env python3
"""Generate bcrypt-hashed credentials for Forge API production auth.

Usage:
    python generate_forge_credentials.py myuser
    python generate_forge_credentials.py myuser mypassword

Set the output as the API_CREDENTIALS env var when starting Forge:
    API_CREDENTIALS='myuser:$2b$12$...' python -m animus_forge.api

Or add to your .env file:
    API_CREDENTIALS=myuser:$2b$12$...

The Commissioner uses FORGE_API_USER and FORGE_API_PASS env vars to
authenticate with Forge at commission time.

Prefer the secure prompt: command-line passwords can appear in shell history
and process listings. Plaintext passwords are never included in the output.
"""

from __future__ import annotations

import getpass
import sys

import bcrypt


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <username> [password]")
        print("If password is omitted, you will be prompted securely.")
        sys.exit(1)

    username = sys.argv[1]

    if len(sys.argv) >= 3:
        pw = sys.argv[2]
    else:
        pw = getpass.getpass(f"Enter password for '{username}': ")
        confirm = getpass.getpass("Confirm password: ")
        if pw != confirm:
            print("Passwords do not match.", file=sys.stderr)
            sys.exit(1)

    hashed = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
    print("\nAdd this to your Forge .env file or environment:")
    print(f"  API_CREDENTIALS='{username}:{hashed}'")
    print("\nCommissioner environment variables:")
    print(f"  FORGE_API_USER='{username}'")
    print("  Set FORGE_API_PASS to the same password through your secret manager.")
    print("\nOr export directly before starting Forge:")
    print(f"  export API_CREDENTIALS='{username}:{hashed}'")


if __name__ == "__main__":
    main()
