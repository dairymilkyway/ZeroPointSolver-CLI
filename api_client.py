import sys
import time
import requests

API_BASE = "https://zeropoint.to/api/zerosolver-api"
MAX_RETRIES = 3


class ZeroSolverError(Exception):
    pass


class ZeroSolverClient:
    def __init__(self, api_key):
        self.headers = {
            "X-API-Key": api_key,
            "Content-Type": "application/json",
        }

    def _request(self, method, path, **kwargs):
        url = f"{API_BASE}{path}"
        for attempt in range(MAX_RETRIES + 1):
            try:
                r = requests.request(method, url, headers=self.headers, **kwargs)
            except requests.exceptions.RequestException as e:
                raise SystemExit(f"Network error: {e}")

            if r.status_code == 401:
                raise SystemExit("Error 401: Invalid API key")
            if r.status_code == 403:
                raise SystemExit("Error 403: API key has been disabled")
            if r.status_code == 402:
                data = r.json()
                print("Error 402: Insufficient Solver Credits")
                print(f"  Required: {data.get('required', '?')} credits")
                print(f"  Available: {data.get('available', '?')} credits")
                print(f"  Cost per success: {data.get('cost_per_success', '?')} credits")
                sys.exit(1)
            if r.status_code == 429:
                data = r.json()
                retry_s = data.get("retryAfterSeconds") or data.get("retryAfterMs") or data.get("retry_after_ms")
                if isinstance(retry_s, (int, float)):
                    wait = retry_s if retry_s < 100 else retry_s / 1000
                    print(f"  Rate limited — waiting {wait:.0f}s...")
                    time.sleep(wait)
                    continue
                detail = data.get("error", r.text[:200])
                raise SystemExit(f"Error 429: {detail}")
            if r.status_code in (500, 503):
                if attempt < MAX_RETRIES:
                    wait = 5 * (attempt + 1)
                    print(f"Service temporarily unavailable ({r.status_code}). Retrying in {wait}s (attempt {attempt + 1}/{MAX_RETRIES})...")
                    time.sleep(wait)
                    continue
                raise SystemExit(f"Error {r.status_code}: ZeroSolver service temporarily unavailable")
            if r.status_code == 400:
                data = r.json()
                raise SystemExit(f"Error 400: {data.get('error', 'Bad request')}")
            if r.status_code == 409:
                data = r.json()
                print(f"Error 409: {data.get('error', 'Conflict - job may already exist')}")
                job_id = data.get("job_id")
                if job_id:
                    print(f"  Existing Job ID: {job_id}")
                    return data
                sys.exit(1)
            r.raise_for_status()
            return r.json()

    def get_credits(self):
        return self._request("GET", "/credits")

    def submit(self, accounts, captcha_type="ingame"):
        payload = {"accounts": accounts}
        if captcha_type != "ingame":
            payload["captcha_type"] = captcha_type
        return self._request("POST", "/submit", json=payload)

    def get_status(self, job_id):
        return self._request("GET", f"/status/{job_id}")

    def download(self, job_id, filename):
        url = f"{API_BASE}/download/{job_id}/{filename}"
        r = requests.get(url, headers=self.headers)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.text

    def cancel(self, job_id):
        return self._request("POST", f"/cancel/{job_id}")

    def get_active(self):
        return self._request("GET", "/active")
