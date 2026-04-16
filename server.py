from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse
import uvicorn
import threading
from fastmcp import FastMCP
import httpx
import os
from typing import Optional

mcp = FastMCP("habanero")

BASE_URL = "https://api.crossref.org"
USER_AGENT = "habanero-mcp/1.0 (mailto:admin@example.com)"


@mcp.tool()
async def search_works(
    query: Optional[str] = None,
    doi: Optional[str] = None,
    filter: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    sort: Optional[str] = None,
    order: Optional[str] = None,
    select: Optional[str] = None,
) -> dict:
    """Search Crossref for scholarly works (articles, books, datasets, etc.) using the /works route.
    Use this when the user wants to find publications by query terms, DOI, author, title, funder,
    or any other metadata. Supports filtering, sorting, pagination, and field selection."""
    async with httpx.AsyncClient() as client:
        if doi:
            url = f"{BASE_URL}/works/{doi}"
            response = await client.get(url, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            return response.json()
        else:
            url = f"{BASE_URL}/works"
            params = {}
            if query:
                params["query"] = query
            if filter:
                params["filter"] = filter
            if limit:
                params["rows"] = limit
            if offset:
                params["offset"] = offset
            if sort:
                params["sort"] = sort
            if order:
                params["order"] = order
            if select:
                params["select"] = select
            response = await client.get(url, params=params, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            return response.json()


@mcp.tool()
async def get_citation_count(doi: str) -> dict:
    """Retrieve the citation count for a specific DOI using the Crossref citation counts API.
    Use this when the user wants to know how many times a paper has been cited."""
    async with httpx.AsyncClient() as client:
        url = f"https://doi.org/api/handles/{doi}"
        # Use Crossref works endpoint to get is-referenced-by-count
        works_url = f"{BASE_URL}/works/{doi}"
        response = await client.get(
            works_url,
            params={"select": "DOI,is-referenced-by-count,title"},
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
        data = response.json()
        result = data.get("message", {})
        return {
            "doi": doi,
            "citation_count": result.get("is-referenced-by-count"),
            "title": result.get("title", []),
        }


@mcp.tool()
async def get_content_negotiation(
    doi: str,
    format: str = "bibtex",
    style: Optional[str] = None,
    locale: str = "en-US",
) -> dict:
    """Retrieve a citation or metadata for a DOI in a specific format using content negotiation.
    Use this when the user wants a formatted citation (BibTeX, RIS, APA, MLA, etc.) for a given DOI."""
    format_map = {
        "bibtex": "application/x-bibtex",
        "ris": "application/x-research-info-systems",
        "turtle": "text/turtle",
        "rdf-xml": "application/rdf+xml",
        "text": "text/x-bibliography",
        "crossref-xml": "application/vnd.crossref.unixref+xml",
        "datacite-xml": "application/vnd.datacite.datacite+xml",
        "citeproc-json": "application/vnd.citationstyles.csl+json",
        "crossref-tdm": "application/vnd.crossref.unixref+xml",
        "json": "application/json",
    }

    content_type = format_map.get(format.lower(), format)

    if format.lower() == "text" and style:
        content_type = f"text/x-bibliography; style={style}"
        if locale:
            content_type += f"; locale={locale}"

    async with httpx.AsyncClient(follow_redirects=True) as client:
        url = f"https://doi.org/{doi}"
        headers = {
            "Accept": content_type,
            "User-Agent": USER_AGENT,
        }
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        text = response.text
        return {
            "doi": doi,
            "format": format,
            "content_type": content_type,
            "citation": text,
        }


@mcp.tool()
async def search_funders(
    query: Optional[str] = None,
    funder_id: Optional[str] = None,
    limit: int = 20,
    works: bool = False,
) -> dict:
    """Search or look up funding organizations in Crossref using the /funders route.
    Use this when the user wants to find funders by name or retrieve information about a
    specific funder by ID, including works they have funded."""
    async with httpx.AsyncClient() as client:
        if funder_id:
            if works:
                url = f"{BASE_URL}/funders/{funder_id}/works"
            else:
                url = f"{BASE_URL}/funders/{funder_id}"
            params = {}
            if works:
                params["rows"] = limit
            response = await client.get(url, params=params, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            return response.json()
        else:
            url = f"{BASE_URL}/funders"
            params = {"rows": limit}
            if query:
                params["query"] = query
            response = await client.get(url, params=params, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            return response.json()


@mcp.tool()
async def search_journals(
    query: Optional[str] = None,
    issn: Optional[str] = None,
    works: bool = False,
    limit: int = 20,
) -> dict:
    """Search for journals or retrieve journal metadata from Crossref using the /journals route.
    Use this when the user wants to find journals by name, ISSN, or explore works published
    in a specific journal."""
    async with httpx.AsyncClient() as client:
        if issn:
            if works:
                url = f"{BASE_URL}/journals/{issn}/works"
            else:
                url = f"{BASE_URL}/journals/{issn}"
            params = {}
            if works:
                params["rows"] = limit
            response = await client.get(url, params=params, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            return response.json()
        else:
            url = f"{BASE_URL}/journals"
            params = {"rows": limit}
            if query:
                params["query"] = query
            response = await client.get(url, params=params, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            return response.json()


@mcp.tool()
async def get_doi_agency(doi: str) -> dict:
    """Look up the registration agency (e.g. Crossref, DataCite, ORCID) responsible for minting
    a given DOI. Use this when the user wants to know who registered a DOI or needs to route
    DOI resolution to the correct agency."""
    async with httpx.AsyncClient() as client:
        url = f"{BASE_URL}/works/{doi}/agency"
        response = await client.get(url, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def get_random_dois(count: int = 10) -> dict:
    """Retrieve a set of random DOIs from Crossref. Use this when the user wants sample DOIs
    for testing, exploration, or demonstration purposes."""
    async with httpx.AsyncClient() as client:
        url = f"{BASE_URL}/works"
        params = {
            "sample": min(count, 100),
            "select": "DOI,title,author,published",
        }
        response = await client.get(url, params=params, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        data = response.json()
        items = data.get("message", {}).get("items", [])
        dois = [item.get("DOI") for item in items if item.get("DOI")]
        return {
            "count": len(dois),
            "dois": dois,
            "items": items,
        }


@mcp.tool()
async def search_members(
    query: Optional[str] = None,
    member_id: Optional[int] = None,
    works: bool = False,
    limit: int = 20,
) -> dict:
    """Search for Crossref member organizations (publishers) or look up a specific member by ID
    using the /members route. Use this when the user wants to find publishers registered with
    Crossref or explore works from a specific publisher."""
    async with httpx.AsyncClient() as client:
        if member_id:
            if works:
                url = f"{BASE_URL}/members/{member_id}/works"
            else:
                url = f"{BASE_URL}/members/{member_id}"
            params = {}
            if works:
                params["rows"] = limit
            response = await client.get(url, params=params, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            return response.json()
        else:
            url = f"{BASE_URL}/members"
            params = {"rows": limit}
            if query:
                params["query"] = query
            response = await client.get(url, params=params, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            return response.json()




_SERVER_SLUG = "sckott-habanero"

def _track(tool_name: str, ua: str = ""):
    try:
        import urllib.request, json as _json
        data = _json.dumps({"slug": _SERVER_SLUG, "event": "tool_call", "tool": tool_name, "user_agent": ua}).encode()
        req = urllib.request.Request("https://www.volspan.dev/api/analytics/event", data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=1)
    except Exception:
        pass

async def health(request):
    return JSONResponse({"status": "ok", "server": mcp.name})

async def tools(request):
    registered = await mcp.list_tools()
    tool_list = [{"name": t.name, "description": t.description or ""} for t in registered]
    return JSONResponse({"tools": tool_list, "count": len(tool_list)})

sse_app = mcp.http_app(transport="sse")

app = Starlette(
    routes=[
        Route("/health", health),
        Route("/tools", tools),
        Mount("/", sse_app),
    ],
    lifespan=sse_app.lifespan,
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
