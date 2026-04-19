"""OCLC Worldcat Metadata API service: batch search and MARC/MARCXML generation."""
from typing import TYPE_CHECKING, Any, Optional
import requests

from src.shared.constants import (
    BATCH_SIZE,
    DEFAULT_HEADERS,
    OCLC_API_BASE_URL,
    SEARCH_FIELD_MAPPING,
)

if TYPE_CHECKING:
    from src.shared.oclc_token_manager import OCLCTokenManager

class OCLCService:
    """Service for Worldcat Metadata API search and bib retrieval."""
    def __init__(self, oclc_token_manager: "OCLCTokenManager") -> None:
        self._token_manager = oclc_token_manager
        self._session = requests.Session()

    def _auth_headers(self) -> dict[str, str]:
        token = self._token_manager.get_shared_token()
        h = dict(DEFAULT_HEADERS)
        h["Authorization"] = f"Bearer {token}"
        return h

    def batch_search(
        self,
        books: list[dict[str, Any]],
        append_query: Optional[str] = None,
        sorting_order: Optional[str] = None,
        is_refining: Optional[bool] = None,
    ) -> tuple[list[dict[str, Any]], Optional[int]]:
        """Call Worldcat Metadata API search/brief-bibs for the given books."""
        base = OCLC_API_BASE_URL.rstrip("/")
        url = f"{base}/search/brief-bibs"
        all_results: list[dict[str, Any]] = []
        usage_remaining: Optional[int] = None

        for i in range(0, len(books), BATCH_SIZE):
            chunk = books[i : i + BATCH_SIZE]
            q_parts = []
            for book in chunk:
                for field, mapped in SEARCH_FIELD_MAPPING.items():
                    val = book.get(field) or book.get(mapped)
                    if val:
                        q_parts.append(f"{mapped}:{val}")
                        break
            q = " OR ".join(q_parts) if q_parts else ""
            if append_query:
                q = f"({q}) AND ({append_query})" if q else append_query
            params: dict[str, Any] = {"q": q} if q else {}
            if sorting_order is not None:
                params["orderBy"] = sorting_order
            if is_refining is not None:
                params["isRefining"] = str(is_refining).lower()

            resp = self._session.get(
                url,
                params=params,
                headers=self._auth_headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            brief_records = data.get("briefRecords") or data.get("briefBibs") or []
            if isinstance(brief_records, list):
                all_results.extend(brief_records)
            else:
                all_results.append(brief_records)
            rem = resp.headers.get("X-Usage-Remaining") or resp.headers.get("Usage-Remaining")
            if rem is not None:
                try:
                    usage_remaining = int(rem)
                except ValueError:
                    pass

        return all_results, usage_remaining

    def generate_xml(
        self,
        oclc_numbers: list[str],
        format_type: str = "marcxml",
    ) -> str:
        """Call manage/bibs/{oclc_number} with Accept application/marcxml+xml or application/marc."""
        base = OCLC_API_BASE_URL.rstrip("/")
        if format_type == "marcxml":
            accept = "application/marcxml+xml"
        else:
            accept = "application/marc"
        headers = self._auth_headers()
        headers["Accept"] = accept
        parts: list[str] = []
        for oclc_number in oclc_numbers:
            url = f"{base}/manage/bibs/{oclc_number}"
            try:
                resp = self._session.get(url, headers=headers, timeout=30)
                resp.raise_for_status()
                ct = resp.headers.get("Content-Type", "")
                if "xml" in ct or "marc" in ct:
                    text = resp.text if hasattr(resp, "text") else resp.content.decode("utf-8", errors="replace")
                    parts.append(text)
            except requests.RequestException:
                continue
        return "\n".join(parts)
