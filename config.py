import os

def load_api_key():
    api_key = os.environ.get("X-API-Key")
    if api_key:
        return api_key
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    if key.strip() == "X-API-Key":
                        return value.strip()
    raise SystemExit(
        "Error: X-API-Key not found.\n"
        "  Set it in .env as: X-API-Key = ZP_ZeroSolver_YourKey\n"
        "  Or set the X-API-Key environment variable."
    )
