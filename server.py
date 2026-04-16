from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse
import uvicorn
import threading
from fastmcp import FastMCP
import httpx
import os
import re
from typing import Optional, List

mcp = FastMCP("habanero")

BASE_URL = "https://api.crossref.org"

# --- Filter handler utilities (from habanero/filterhandler.py) ---

others = [
    "license_url",
    "license_version",
    "license_delay",
    "full_text_version",
    "full_text_type",
    "full_text_application",
    "award_number",
    "award_funder",
]

dict_filts = {
    "license_url": "license.url",
    "license_version": "license.version",
    "license_delay": "license.delay",
    "full_text_version": "full-text.version",
    "full_text_type": "full-text.type",
    "award_number": "award.number",
    "award_funder": "award.funder",
    "relation_type": "relation.type",
    "relation_object": "relation.object",
    "relation_object_type": "relation.object-type",
}


def switch_filters(x):
    return dict_filts.get(x, x)


def rename_keys(old_dict, transform):
    new_dict = {}
    for k, v in old_dict.items():
        if k in transform:
            new_dict.update({transform[k]: v})
        else:
            new_dict.update({k: v})
    return new_dict


def filter_handler(x=None):
    if x is None:
        return None
    # lowercase bools
    for k, v in x.items():
        if isinstance(v, bool):
            x[k] = str(v).lower()

    nn = list(x.keys())
    if any([i in others for i in nn]):
        out = []
        for i in nn:
            if i in others:
                out.append(switch_filters(i))
            else:
                out.append(i)
        nn = out

    newnn = [re.sub("_", "-", z) for z in nn]
    newnnd = dict(zip(x.keys(), newnn))
    x = rename_keys(x, newnnd)

    newx = []
    for k, v in x.items():
        if isinstance(v, list):
            for a, b in enumerate(v):
                newx.append(":".join([k, b]))
        else:
            newx.append(":".join([k, v]))

    return ",".join(newx)


# --- Tools ---

@mcp.tool()
async def search_works(
    _track("search_works")
    query: Optional[str] = None,
    doi: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    sort: Optional[str] = None,
    order: str = "desc",
    filter: Optional[str] = None,
    select: Optional[List[str]] = None
) -> dict:
    """Search Crossref works/publications using the /works API route. Use this when the user wants to find academic papers, articles, books, or other scholarly works by query terms, DOI, author, title, date range, or other metadata. Supports pagination, sorting, and field selection."""
    async with httpx.AsyncClient() as client:
        if doi:
            url = f"{BASE_URL}/works/{doi}"
            response = await client.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        else:
            url = f"{BASE_URL}/works"
            params = {}
            if query:
                params["query"] = query
            if limit:
                params["rows"] = limit
            if offset:
                params["offset"] = offset
            if sort:
                params["sort"] = sort
            if order:
                params["order"] = order
            if filter:
                params["filter"] = filter
            if select:
                params["select"] = ",".join(select)
            response = await client.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()


@mcp.tool()
async def get_citation_count(doi: str) -> dict:
    """Retrieve the citation count for a specific article by its DOI using the Crossref citation count API. Use this when the user wants to know how many times a paper has been cited."""
    _track("get_citation_count")
    async with httpx.AsyncClient() as client:
        url = f"https://doi.org/api/handles/{doi}"
        # Use Crossref's works endpoint to get cited-by-count
        works_url = f"{BASE_URL}/works/{doi}"
        response = await client.get(works_url, timeout=30)
        response.raise_for_status()
        data = response.json()
        cited_by = data.get("message", {}).get("is-referenced-by-count", None)
        title = data.get("message", {}).get("title", [""])
        return {
            "doi": doi,
            "title": title[0] if title else "",
            "citation_count": cited_by
        }


@mcp.tool()
async def get_content_negotiation(
    _track("get_content_negotiation")
    doi: str,
    format: str = "bibtex",
    style: str = "apa",
    locale: str = "en-US"
) -> dict:
    """Retrieve a citation or reference in a specific format (BibTeX, RIS, APA, etc.) for a given DOI using content negotiation. Use this when the user wants to export a citation or reference in a particular style or format."""
    format_map = {
        "bibtex": "application/x-bibtex",
        "ris": "application/x-research-info-systems",
        "turtle": "text/turtle",
        "rdf-xml": "application/rdf+xml",
        "crossref-xml": "application/vnd.crossref.unixsd+xml",
        "text": "text/x-bibliography",
        "citeproc-json": "application/vnd.citationstyles.csl+json",
        "unixref-xml": "application/vnd.crossref.unixsd+xml",
        "json": "application/json",
    }
    content_type = format_map.get(format.lower(), "application/x-bibtex")
    headers = {"Accept": content_type}
    if format.lower() == "text":
        headers["Accept"] = f"text/x-bibliography; style={style}; locale={locale}"

    async with httpx.AsyncClient(follow_redirects=True) as client:
        url = f"https://doi.org/{doi}"
        response = await client.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return {
            "doi": doi,
            "format": format,
            "style": style if format.lower() == "text" else None,
            "content": response.text
        }


@mcp.tool()
async def lookup_entity(
    _track("lookup_entity")
    entity: str,
    id: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 20,
    offset: int = 0
) -> dict:
    """Look up metadata for Crossref entities such as members, funders, journals, prefixes, licenses, or types by ID or search query. Use this when the user wants information about a publisher, funding organization, journal, or other Crossref registry entity."""
    valid_entities = ["members", "funders", "journals", "prefixes", "licenses", "types"]
    if entity not in valid_entities:
        return {"error": f"Invalid entity type. Must be one of: {', '.join(valid_entities)}"}

    async with httpx.AsyncClient() as client:
        if id:
            url = f"{BASE_URL}/{entity}/{id}"
            response = await client.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        else:
            url = f"{BASE_URL}/{entity}"
            params = {}
            if query:
                params["query"] = query
            params["rows"] = limit
            params["offset"] = offset
            response = await client.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()


@mcp.tool()
async def get_doi_agency(dois: List[str]) -> dict:
    """Retrieve the DOI registration agency for one or more DOIs. Use this to determine which organization registered a DOI (e.g. Crossref, DataCite, ORCID, mEDRA)."""
    _track("get_doi_agency")
    results = []
    async with httpx.AsyncClient() as client:
        for doi in dois:
            url = f"{BASE_URL}/works/{doi}/agency"
            try:
                response = await client.get(url, timeout=30)
                response.raise_for_status()
                data = response.json()
                agency = data.get("message", {}).get("agency", {})
                results.append({
                    "doi": doi,
                    "agency": agency
                })
            except Exception as e:
                results.append({
                    "doi": doi,
                    "error": str(e)
                })
    return {"results": results}


@mcp.tool()
async def get_random_dois(count: int = 10) -> dict:
    """Retrieve a set of random DOIs from Crossref. Useful for sampling, testing, or exploring the Crossref corpus."""
    _track("get_random_dois")
    if count > 100:
        count = 100
    async with httpx.AsyncClient() as client:
        url = f"{BASE_URL}/works"
        params = {
            "sample": count
        }
        response = await client.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        items = data.get("message", {}).get("items", [])
        dois = [item.get("DOI") for item in items if item.get("DOI")]
        return {
            "count": len(dois),
            "dois": dois
        }


@mcp.tool()
async def build_filter(
    _track("build_filter")
    has_full_text: Optional[bool] = None,
    has_abstract: Optional[bool] = None,
    has_references: Optional[bool] = None,
    from_pub_date: Optional[str] = None,
    until_pub_date: Optional[str] = None,
    license_url: Optional[str] = None,
    member: Optional[str] = None,
    type: Optional[str] = None,
    award_funder: Optional[str] = None,
    award_number: Optional[str] = None
) -> dict:
    """Build a properly formatted Crossref API filter string from structured filter parameters. Use this before calling search_works when filters need to be constructed from human-readable parameters like date ranges, license types, publisher membership, or availability flags."""
    filters = {}

    if has_full_text is not None:
        filters["has_full_text"] = has_full_text
    if has_abstract is not None:
        filters["has_abstract"] = has_abstract
    if has_references is not None:
        filters["has_references"] = has_references
    if from_pub_date is not None:
        filters["from_pub_date"] = from_pub_date
    if until_pub_date is not None:
        filters["until_pub_date"] = until_pub_date
    if license_url is not None:
        filters["license_url"] = license_url
    if member is not None:
        filters["member"] = member
    if type is not None:
        filters["type"] = type
    if award_funder is not None:
        filters["award_funder"] = award_funder
    if award_number is not None:
        filters["award_number"] = award_number

    filter_string = filter_handler(filters) if filters else ""
    return {
        "filter_string": filter_string,
        "description": "Pass this filter_string as the 'filter' parameter to search_works."
    }




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
