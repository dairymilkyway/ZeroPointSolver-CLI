import os

def _load_key(env_var, file_key, prefix_hint):
    api_key = os.environ.get(env_var)
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
                    if key.strip() == file_key:
                        return value.strip()
    raise SystemExit(
        f"Error: {file_key} not found.\n"
        f"  Set it in .env as: {file_key} = {prefix_hint}\n"
        f"  Or set the {env_var} environment variable."
    )

def load_zsolver_key():
    return _load_key("X-API-Key-Solver", "X-API-Key-Solver", "ZP_ZeroSolver_YourKey")

def load_faceunlock_key():
    return _load_key("X-API-Key-Face_Unlock", "X-API-Key-Face_Unlock", "ZP_FaceUnlock_YourKey")
