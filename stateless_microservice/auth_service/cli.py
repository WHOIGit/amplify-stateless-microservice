#!/usr/bin/env python3
"""
CLI tool for managing authentication tokens.

Usage:
    auth-cli create mytoken --scopes read write --ttl 365
    auth-cli list
    auth-cli revoke <token_id>
    auth-cli info <token_id>
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime

import httpx

# Use PORT env var if set (for running inside container), otherwise default to 8000
DEFAULT_PORT = os.getenv("PORT", "8000")
DEFAULT_AUTH_URL = f"http://localhost:{DEFAULT_PORT}"


async def create_token(auth_url: str, name: str, scopes: list[str], ttl_days: int | None):
    """Create a new token."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{auth_url}/auth/tokens",
                json={
                    "name": name,
                    "scopes": scopes,
                    "ttl_days": ttl_days,
                    "metadata": {}
                },
                timeout=10.0
            )

            if response.status_code == 201:
                data = response.json()
                print("\nToken created successfully!")
                print(f"\nToken: {data['token']}")
                print(f"Token ID: {data['token_id']}")
                print(f"Name: {data['name']}")
                print(f"Scopes: {', '.join(data['scopes'])}")
                print(f"Created: {data['created_at']}")
                if data['expires_at']:
                    print(f"Expires: {data['expires_at']}")
                else:
                    print("Expires: Never")
                print("\nIMPORTANT: Save this token now! It will not be shown again.\n")
                return 0
            else:
                print(f"Error: {response.status_code} - {response.text}", file=sys.stderr)
                return 1

        except httpx.RequestError as e:
            print(f"Connection error: {e}", file=sys.stderr)
            return 1


async def list_tokens(auth_url: str, include_revoked: bool):
    """List all tokens."""
    async with httpx.AsyncClient() as client:
        try:
            params = {"include_revoked": include_revoked}
            response = await client.get(
                f"{auth_url}/auth/tokens",
                params=params,
                timeout=10.0
            )

            if response.status_code == 200:
                data = response.json()
                tokens = data['tokens']

                if not tokens:
                    print("No tokens found.")
                    return 0

                print(f"\nTotal tokens: {data['total']}\n")
                print(f"{'ID':<40} {'Name':<20} {'Scopes':<30} {'Expires':<20} {'Revoked':<10}")
                print("-" * 130)

                for token in tokens:
                    token_id = token['token_id'][:36]
                    name = token['name'][:18]
                    scopes = ', '.join(token['scopes'])[:28]
                    expires = token['expires_at'][:19] if token['expires_at'] else "Never"
                    revoked = "Yes" if token['revoked'] else "No"

                    print(f"{token_id:<40} {name:<20} {scopes:<30} {expires:<20} {revoked:<10}")

                print()
                return 0
            else:
                print(f"Error: {response.status_code} - {response.text}", file=sys.stderr)
                return 1

        except httpx.RequestError as e:
            print(f"Connection error: {e}", file=sys.stderr)
            return 1


async def get_token_info(auth_url: str, token_id: str):
    """Get detailed information about a token."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{auth_url}/auth/tokens/{token_id}",
                timeout=10.0
            )

            if response.status_code == 200:
                data = response.json()
                print(f"\nToken Information:")
                print(f"  ID: {data['token_id']}")
                print(f"  Name: {data['name']}")
                print(f"  Scopes: {', '.join(data['scopes'])}")
                print(f"  Created: {data['created_at']}")
                print(f"  Expires: {data['expires_at'] if data['expires_at'] else 'Never'}")
                print(f"  Revoked: {'Yes' if data['revoked'] else 'No'}")
                if data['revoked_at']:
                    print(f"  Revoked At: {data['revoked_at']}")
                if data.get('metadata'):
                    print(f"  Metadata: {data['metadata']}")
                print()
                return 0
            elif response.status_code == 404:
                print(f"Token not found: {token_id}", file=sys.stderr)
                return 1
            else:
                print(f"Error: {response.status_code} - {response.text}", file=sys.stderr)
                return 1

        except httpx.RequestError as e:
            print(f"Connection error: {e}", file=sys.stderr)
            return 1


async def revoke_token(auth_url: str, token_id: str):
    """Revoke a token."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{auth_url}/auth/tokens/{token_id}/revoke",
                json={},
                timeout=10.0
            )

            if response.status_code == 200:
                data = response.json()
                print(f"\nToken revoked successfully!")
                print(f"  Token ID: {data['token_id']}")
                print(f"  Revoked At: {data['revoked_at']}\n")
                return 0
            elif response.status_code == 404:
                print(f"Token not found: {token_id}", file=sys.stderr)
                return 1
            else:
                print(f"Error: {response.status_code} - {response.text}", file=sys.stderr)
                return 1

        except httpx.RequestError as e:
            print(f"Connection error: {e}", file=sys.stderr)
            return 1


def main():
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Manage AMPLIfy authentication tokens",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "--auth-url",
        default=DEFAULT_AUTH_URL,
        help=f"Auth service URL (default: {DEFAULT_AUTH_URL})"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Create token
    create_parser = subparsers.add_parser("create", help="Create a new token")
    create_parser.add_argument("name", help="Token name (unique identifier)")
    create_parser.add_argument("--scopes", nargs="+", required=True, help="Token scopes")
    create_parser.add_argument("--ttl", type=int, help="Days until expiration (omit for no expiration)")

    # List tokens
    list_parser = subparsers.add_parser("list", help="List all tokens")
    list_parser.add_argument("--all", action="store_true", help="Include revoked tokens")

    # Get token info
    info_parser = subparsers.add_parser("info", help="Get token information")
    info_parser.add_argument("token_id", help="Token ID")

    # Revoke token
    revoke_parser = subparsers.add_parser("revoke", help="Revoke a token")
    revoke_parser.add_argument("token_id", help="Token ID to revoke")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Execute command
    if args.command == "create":
        return asyncio.run(create_token(args.auth_url, args.name, args.scopes, args.ttl))
    elif args.command == "list":
        return asyncio.run(list_tokens(args.auth_url, args.all))
    elif args.command == "info":
        return asyncio.run(get_token_info(args.auth_url, args.token_id))
    elif args.command == "revoke":
        return asyncio.run(revoke_token(args.auth_url, args.token_id))
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
