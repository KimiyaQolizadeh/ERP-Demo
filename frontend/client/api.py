import json

import requests


class APIError(Exception):
    pass


class APIClient:
    def __init__(self, base_url: str, user_id: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.user_id = user_id

    def with_user(self, user_id: str) -> "APIClient":
        return APIClient(self.base_url, user_id=user_id)

    def _headers(self) -> dict:
        return {"X-User-Id": self.user_id} if self.user_id else {}

    def _request(self, method: str, path: str, *, params=None, json=None, timeout=30):
        url = f"{self.base_url}{path}"
        r = requests.request(method, url, headers=self._headers(), params=params, json=json, timeout=timeout)

        # If backend returns error, surface it clearly
        if r.status_code >= 400:
            # Try to parse JSON error
            try:
                detail = r.json()
            except Exception:
                detail = r.text[:500]  # show first 500 chars (HTML/plain)
            raise APIError(f"{method} {path} -> {r.status_code}: {detail}")

        # Parse JSON safely
        try:
            return r.json()
        except Exception:
            raise APIError(f"{method} {path} -> Response was not JSON. Body: {r.text[:500]}")

    # -------- Core / Health --------
    def health(self) -> dict:
        return self._request("GET", "/health", timeout=5)

    # -------- Users --------
    def list_login_options(self) -> list[dict]:
        return self._request("GET", "/users/login-options", timeout=15)

    def list_users(self) -> list[dict]:
        return self._request("GET", "/users", timeout=15)

    # -------- Projects --------
    def list_projects(self, status: str | None = None, pm_user_id: str | None = None) -> list[dict]:
        params: dict = {}
        if status:
            params["status"] = status
        if pm_user_id:
            params["pm_user_id"] = pm_user_id
        return self._request("GET", "/projects", params=(params or None), timeout=30)

    def get_project(self, project_id: str) -> dict:
        return self._request("GET", f"/projects/{project_id}", timeout=30)

    def create_project(self, payload: dict) -> dict:
        return self._request("POST", "/projects", json=payload, timeout=30)

    def update_project(self, project_id: str, payload: dict) -> dict:
        return self._request("PATCH", f"/projects/{project_id}", json=payload, timeout=30)

    def replace_project_rates(self, project_id: str, rates: list[dict]) -> list[dict]:
        return self._request("PUT", f"/projects/{project_id}/rates", json=rates, timeout=30)

    def project_health(
        self,
        project_id: str,
        *,
        bucket_days: int = 14,
        lookback_buckets: int = 12,
        start_date: str | None = None,
        end_date: str | None = None,
        approved_only: bool = True,
    ) -> dict:
        params: dict = {
            "bucket_days": bucket_days,
            "lookback_buckets": lookback_buckets,
            "approved_only": str(bool(approved_only)).lower(),
        }
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        return self._request("GET", f"/projects/{project_id}/health", params=params, timeout=45)

    def project_risk_explanation(
        self,
        project_id: str,
        *,
        bucket_days: int = 14,
        lookback_buckets: int = 12,
        start_date: str | None = None,
        end_date: str | None = None,
        approved_only: bool = True,
    ) -> dict:
        payload: dict = {
            "bucket_days": bucket_days,
            "lookback_buckets": lookback_buckets,
            "approved_only": bool(approved_only),
            "start_date": start_date,
            "end_date": end_date,
        }
        return self._request("POST", f"/projects/{project_id}/risk-explanation", json=payload, timeout=60)

    # -------- Reports --------
    def dashboard(self, month: str) -> dict:
        return self._request("GET", "/reports/dashboard", params={"month": month}, timeout=30)

    def readiness(self, month: str) -> dict:
        return self._request("GET", "/reports/invoice-readiness", params={"month": month}, timeout=30)

    def anomalies(self, month: str, metric: str = "spend_to_date") -> dict:
        return self._request("GET", "/reports/anomalies", params={"month": month, "metric": metric}, timeout=30)

    # -------- Search --------
    def search_projects(self, q: str, limit: int = 20) -> list[dict]:
        return self._request("GET", "/search/projects", params={"q": q, "limit": limit}, timeout=20)

    def search_users(self, q: str, limit: int = 20) -> list[dict]:
        return self._request("GET", "/search/users", params={"q": q, "limit": limit}, timeout=20)

    # -------- Timesheets --------
    def list_timesheets(self, status: str | None = None) -> list[dict]:
        params = {"status": status} if status else None
        return self._request("GET", "/timesheets", params=params, timeout=30)

    def create_timesheet(self, payload: dict) -> dict:
        return self._request("POST", "/timesheets", json=payload, timeout=30)

    def add_entry(self, timesheet_id: str, payload: dict) -> dict:
        return self._request("POST", f"/timesheets/{timesheet_id}/entries", json=payload, timeout=30)

    def list_time_entries(self, timesheet_id: str) -> list[dict]:
        return self._request("GET", f"/timesheets/{timesheet_id}/entries", timeout=30)

    def get_timesheet(self, timesheet_id: str) -> dict:
        return self._request("GET", f"/timesheets/{timesheet_id}", timeout=30)

    def submit_timesheet(self, timesheet_id: str) -> dict:
        return self._request("POST", f"/timesheets/{timesheet_id}/submit", timeout=30)

    def reopen_timesheet(self, timesheet_id: str) -> dict:
        return self._request("POST", f"/timesheets/{timesheet_id}/reopen", timeout=30)

    # -------- Approvals --------
    def pending_approvals(self) -> list[dict]:
        return self._request("GET", "/approvals/pending", timeout=30)

    def approve_timesheet(self, timesheet_id: str) -> dict:
        return self._request("POST", f"/approvals/{timesheet_id}/approve", timeout=30)

    def reject_timesheet(self, timesheet_id: str, reason: str) -> dict:
        return self._request("POST", f"/approvals/{timesheet_id}/reject", json={"reason": reason}, timeout=30)

    # -------- Invoices --------
    def draft_invoice(self, project_id: str, month: str) -> dict:
        return self._request("POST", "/invoices/draft", params={"project_id": project_id, "month": month}, timeout=60)

    def add_adjustment(self, invoice_id: str, description: str, amount: float) -> dict:
        return self._request("PATCH", f"/invoices/{invoice_id}/adjustments",
                             json={"description": description, "amount": amount}, timeout=30)

    def approve_invoice(self, invoice_id: str) -> dict:
        return self._request("POST", f"/invoices/{invoice_id}/approve", timeout=30)

    def export_invoice(self, invoice_id: str) -> dict:
        return self._request("GET", f"/invoices/{invoice_id}/export", timeout=30)

    # -------- Audit --------
    def audit_logs(self, limit: int = 50) -> list[dict]:
        return self._request("GET", "/audit/logs", params={"limit": limit}, timeout=30)

    # -------- AI --------
    def ai_status(self, probe: bool = False) -> dict:
        params = {"probe": "true"} if probe else None
        return self._request("GET", "/ai/status", params=params, timeout=20)

    def ai_improve_notes(self, raw_notes: str, discipline=None, project_name=None) -> dict:
        return self._request("POST", "/ai/improve-notes",
                             json={"raw_notes": raw_notes, "discipline": discipline, "project_name": project_name},
                             timeout=30)

    def ai_classify_billable(self, notes: str, discipline=None, contract_type=None) -> dict:
        return self._request("POST", "/ai/billable/classify",
                             json={"notes": notes, "discipline": discipline, "contract_type": contract_type},
                             timeout=30)

    def ai_parse_timesheet_text(self, text: str, week_start: str, disciplines: list[str], projects: list[dict]) -> dict:
        return self._request("POST", "/ai/parse-timesheet-text",
                             json={"text": text, "week_start": week_start, "disciplines": disciplines, "projects": projects},
                             timeout=60)

    def ai_billable_probability(self, notes: str, threshold: float):
        return self._request("POST", "/ai/billable-probability", json={"notes": notes, "threshold": threshold},
                             timeout=30)

    def ai_explain_risk(self, title: str, metrics: dict):
        return self._request("POST", "/ai/explain-risk", json={"title": title, "metrics": metrics}, timeout=30)

    def ai_accept_suggestion(
        self,
        action: str,
        *,
        entity_type: str = "AI",
        entity_id: str | None = None,
        accepted: bool = True,
        input_payload: dict | None = None,
        output_payload: dict | None = None,
    ) -> dict:
        return self._request(
            "POST",
            "/ai/accept",
            json={
                "action": action,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "accepted": accepted,
                "input": input_payload or {},
                "output": output_payload or {},
            },
            timeout=30,
        )

    def ai_retrieval_index_time_entry(self, entry_id: str) -> dict:
        return self._request("POST", "/ai/retrieval/index-time-entry", json={"entry_id": entry_id}, timeout=30)

    def ai_retrieval_search(
        self,
        query: str,
        *,
        top_k: int = 5,
        source_type: str | None = None,
        project_id: str | None = None,
        month: str | None = None,
    ) -> dict:
        return self._request(
            "POST",
            "/ai/retrieval/search",
            json={
                "query": query,
                "top_k": top_k,
                "source_type": source_type,
                "project_id": project_id,
                "month": month,
            },
            timeout=45,
        )

    def copilot_chat(self, message: str, history: list[dict], month: str | None = None) -> dict:
        return self._request(
            "POST",
            "/copilot/chat",
            json={"message": message, "history": history, "month": month},
            timeout=60,
        )

    def ai_voice_parse(self, wav_bytes: bytes, week_start: str, discipline_choices: list[str], project_name: str):
        files = {"audio": ("audio.wav", wav_bytes, "audio/wav")}
        data = {
            "week_start": week_start,
            "discipline_choices": json.dumps(discipline_choices),
            "project_name": project_name,
        }
        # Kept as a direct request because multipart upload differs from JSON APIs.
        url = f"{self.base_url}/ai/voice/parse"
        r = requests.post(url, headers=self._headers(), files=files, data=data, timeout=120)
        if r.status_code >= 400:
            try:
                detail = r.json()
            except Exception:
                detail = r.text[:500]
            raise APIError(f"POST /ai/voice/parse -> {r.status_code}: {detail}")
        try:
            return r.json()
        except Exception:
            raise APIError(f"POST /ai/voice/parse -> Response was not JSON. Body: {r.text[:500]}")

    def ai_voice_transcribe(self, wav_bytes: bytes) -> dict:
        files = {"audio": ("audio.wav", wav_bytes, "audio/wav")}
        url = f"{self.base_url}/ai/voice/transcribe"
        r = requests.post(url, headers=self._headers(), files=files, timeout=120)
        if r.status_code >= 400:
            try:
                detail = r.json()
            except Exception:
                detail = r.text[:500]
            raise APIError(f"POST /ai/voice/transcribe -> {r.status_code}: {detail}")
        try:
            return r.json()
        except Exception:
            raise APIError(f"POST /ai/voice/transcribe -> Response was not JSON. Body: {r.text[:500]}")

    def ai_voice_synthesize(
        self,
        text: str,
        *,
        voice: str = "alloy",
        response_format: str = "mp3",
        model: str | None = None,
    ) -> tuple[bytes, str]:
        url = f"{self.base_url}/ai/voice/synthesize"
        payload = {"text": text, "voice": voice, "response_format": response_format, "model": model}
        r = requests.post(url, headers=self._headers(), json=payload, timeout=120)
        if r.status_code >= 400:
            try:
                detail = r.json()
            except Exception:
                detail = r.text[:500]
            raise APIError(f"POST /ai/voice/synthesize -> {r.status_code}: {detail}")
        content_type = str(r.headers.get("Content-Type") or f"audio/{response_format}")
        return r.content, content_type

