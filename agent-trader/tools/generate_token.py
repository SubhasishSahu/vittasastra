"""
Agent_Trader — Token Generator
Run this on Mac or PythonAnywhere to get your API token for the iPad dashboard.
Usage: python tools/generate_token.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import USER_EMAIL, SECRET_SALT, generate_token, validate_token

def main():
    print("\nAgent_Trader — Auth Token")
    print("─" * 40)

    if not USER_EMAIL:
        print("❌  USER_EMAIL is not set.")
        print("    Check your .env file: cat .env")
        sys.exit(1)

    if not SECRET_SALT:
        print("❌  SECRET_SALT is not set.")
        print("    Check your .env file: cat .env")
        sys.exit(1)

    print(f"Email:  {USER_EMAIL}")
    print(f"Salt:   {SECRET_SALT[:8]}... (truncated)")

    token = generate_token(USER_EMAIL)
    valid = validate_token(token)

    print(f"\nToken:  {token}")
    print(f"Valid:  {'✅ YES' if valid else '❌ NO — check SECRET_SALT'}")
    print(f"\nUse this token in API calls:")
    print(f"  https://YOURUSERNAME.pythonanywhere.com/api/snapshot?token={token}")
    print()

if __name__ == "__main__":
    main()
