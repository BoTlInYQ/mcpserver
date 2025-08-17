from typing import Any, Dict, List, Optional
import os
import datetime as dt
import httpx
from mcp.server.fastmcp import FastMCP

# ---------- Server ----------
mcp = FastMCP("nyt_article_search_movies", log_level="ERROR")

NYT_API_BASE = "https://api.nytimes.com/svc/search/v2/articlesearch.json"
USER_AGENT = "nyt-articles-movies-mcp/1.0"

NYT_API_KEY = "nV0BauCixsYRAmipCK3EGYll4QAvkYFa" #os.getenv("NYT_API_KEY", "").strip()
if not NYT_API_KEY:
    # We don't raise here so the module can import. Tools will return a helpful error instead.
    pass

# ---------- Helpers ----------
def iso_to_yyyymmdd(d: str) -> Optional[str]:
    """Accept YYYY-MM-DD (or YYYYMMDD) and return YYYYMMDD, else None."""
    if not d:
        return None
    d = d.strip()
    if len(d) == 8 and d.isdigit():   # YYYYMMDD
        return d
    try:
        return dt.datetime.strptime(d, "%Y-%m-%d").strftime("%Y%m%d")
    except Exception:
        return None

async def nyt_get(params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Thin wrapper around the Article Search endpoint with error handling."""
    if not NYT_API_KEY:
        return {"error": "Missing NYT_API_KEY environment variable."}
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    qparams = {**params, "api-key": NYT_API_KEY}
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.get(NYT_API_BASE, params=qparams, headers=headers)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"error": f"Request failed: {e}"}

def format_doc(doc: Dict[str, Any]) -> str:
    headline = (doc.get("headline") or {}).get("main") or "Untitled"
    kicker = (doc.get("headline") or {}).get("kicker") or ""
    byline = (doc.get("byline") or {}).get("original") or "Unknown byline"
    pub_date = (doc.get("pub_date") or "")[:10]
    url = doc.get("web_url") or ""
    summary = doc.get("abstract") or doc.get("snippet") or ""
    critics_pick_flag = doc.get("critics_pick")
    critics_mark = " (Critic's Pick)" if critics_pick_flag == 1 or "critic" in kicker.lower() else ""
    return (
        f"Title: {headline}{critics_mark}\n"
        f"{byline}\n"
        f"Published: {pub_date}\n"
        f"URL: {url}\n"
        f"Summary: {summary}".strip()
    )

def build_movies_review_fq(extra_terms: List[str] = None) -> str:
    """Base filters to constrain to NYT movie reviews; optionally add extra fq terms."""
    terms = []  # No longer constrain to Movies/Review by default
    if extra_terms:
        terms.extend(extra_terms)
    return " AND ".join(terms)

# ---------- Tools ----------
@mcp.tool()
async def search_reviews_by_title(
    title: str,
    start_date: str = "",
    end_date: str = "",
    sort: str = "relevance",
    page: int = 0,
    limit: int = 5
) -> str:
    """
    Search New York Times movie *reviews* by movie title.
    Date filters use publication dates (Article Search params).
    Args:
        title: movie title or keywords to search (e.g., "Oppenheimer")
        start_date: YYYY-MM-DD or YYYYMMDD (inclusive)
        end_date:   YYYY-MM-DD or YYYYMMDD (inclusive)
        sort: "newest" | "oldest" | "relevance"
        page: pagination index (10 results per page)
        limit: number of formatted items to return from this page (default 5)
    """
    begin = iso_to_yyyymmdd(start_date)
    end = iso_to_yyyymmdd(end_date)

    fq = build_movies_review_fq()
    params = {
        "q": title,
        "fq": fq,
        "sort": sort,
        "page": max(0, int(page))
    }
    if begin: params["begin_date"] = begin
    if end:   params["end_date"] = end

    data = await nyt_get(params)
    if not data or "error" in data:
        return f"Unable to fetch results. {data.get('error') if isinstance(data, dict) else ''}".strip()

    docs = (data.get("response") or {}).get("docs") or []
    if not docs:
        return "No reviews found for the given query/date range."
    formatted = [format_doc(d) for d in docs[:max(1, int(limit))]]
    return "\n---\n".join(formatted)

@mcp.tool()
async def get_critics_picks(
    start_date: str = "",
    end_date: str = "",
    sort: str = "relevance",
    page: int = 0,
    limit: int = 5
) -> str:
    """
    Get the most recent NYT movie reviews that are Critics' Picks.
    If dates are supplied, they filter by *publication* date.
    Args mirror search_reviews_by_title.
    """
    begin = iso_to_yyyymmdd(start_date)
    end = iso_to_yyyymmdd(end_date)

    # Constrain to movie reviews + critics picks
    fq_terms = [ 'critics_pick:1' ]  # primary way
    fq = build_movies_review_fq(fq_terms)

    params = {"fq": fq, "sort": sort, "page": max(0, int(page))}
    if begin: params["begin_date"] = begin
    if end:   params["end_date"] = end

    data = await nyt_get(params)
    if not data or "error" in data:
        return f"Unable to fetch results. {data.get('error') if isinstance(data, dict) else ''}".strip()

    docs = (data.get("response") or {}).get("docs") or []

    # Fallback: if critics_pick field is missing/0 but the kicker says "Critic's Pick", include it.
    filtered: List[Dict[str, Any]] = []
    for d in docs:
        kicker = ((d.get("headline") or {}).get("kicker") or "").lower()
        if d.get("critics_pick") == 1 or "critic" in kicker and "pick" in kicker:
            filtered.append(d)

    if not filtered:
        return "No Critics' Pick reviews found for the given criteria."

    formatted = [format_doc(d) for d in filtered[:max(1, int(limit))]]
    return "\n---\n".join(formatted)

if __name__ == "__main__":
    mcp.run(transport="stdio")