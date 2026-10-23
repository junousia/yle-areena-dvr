import httpx
import re
import json
from datetime import datetime, timezone
from .models import YleProgram, Program

AREENA_URL = "https://areena.yle.fi/tv"
_ENV_RE = re.compile(r'window\.envVariables\s*=\s*({.*?});')


def extract_frontend_credentials(html: str) -> tuple[str, str] | None:
    """Reads the app_id/app_key that Areena's own web frontend embeds in its pages."""
    env_match = _ENV_RE.search(html)
    if not env_match:
        return None
    try:
        env_vars = json.loads(env_match.group(1))
    except json.JSONDecodeError:
        return None
    app_id, app_key = env_vars.get("appIdFrontend"), env_vars.get("appKeyFrontend")
    return (app_id, app_key) if app_id and app_key else None


class YleClient:
    def __init__(self, app_id: str | None = None, app_key: str | None = None):
        # Optional overrides (YLE_APP_ID / YLE_APP_KEY); otherwise fetched from Areena on first use.
        self.app_id = app_id
        self.app_key = app_key
        self.base_url = "https://external.api.yle.fi/v1"

    async def _credentials(self, client: httpx.AsyncClient) -> tuple[str, str]:
        if self.app_id and self.app_key:
            return self.app_id, self.app_key
        response = await client.get(AREENA_URL, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True)
        response.raise_for_status()
        found = extract_frontend_credentials(response.text)
        if not found:
            raise RuntimeError(
                "Could not read Yle API credentials from areena.yle.fi. "
                "Set YLE_APP_ID and YLE_APP_KEY in .env."
            )
        self.app_id, self.app_key = found
        return found

    async def search_movies(self, q: str = "", limit: int = 10) -> list[YleProgram]:
        """Searches for movies/programs in Yle Areena."""
        # Note: This endpoint is currently returning 404 for search.
        url = f"{self.base_url}/programs/items.json"
        async with httpx.AsyncClient() as client:
            app_id, app_key = await self._credentials(client)
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "q": q,
            "type": "movie",
            "availability": "ondemand",
            "limit": limit
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return [YleProgram(**item) for item in data.get("data", [])]

    async def get_program_details(self, program_id: str) -> YleProgram:
        """Fetches detailed information for a specific program."""
        url = f"{self.base_url}/programs/items/{program_id}.json"
        async with httpx.AsyncClient() as client:
            app_id, app_key = await self._credentials(client)
            params = {"app_id": app_id, "app_key": app_key}
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return YleProgram(**data.get("data", {}))

    async def scrape_areena_page(self, page_url: str) -> dict[str, list[Program]]:
        """
        Scrapes a Yle Areena page (like Elokuvat list) to find categorized lists of movies/series.
        Returns a dictionary mapping list titles to a list of Programs.
        """
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Origin": "https://areena.yle.fi",
            "Referer": "https://areena.yle.fi/"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(page_url, headers=headers)
            response.raise_for_status()
            html = response.text
            
            # Extract Next.js data
            next_data_match = re.search(r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>', html)
            if not next_data_match:
                print("Could not find __NEXT_DATA__ on the page.")
                return {}
                
            next_data = json.loads(next_data_match.group(1))
            
            # Extract frontend app_id and app_key (explicit overrides win if both are set)
            credentials = (self.app_id, self.app_key) if self.app_id and self.app_key else extract_frontend_credentials(html)
            if not credentials:
                print("Could not read Yle API credentials from the page. Set YLE_APP_ID and YLE_APP_KEY in .env.")
                return {}
            frontend_app_id, frontend_app_key = credentials

            results: dict[str, list[Program]] = {}
            
            try:
                tabs = next_data["props"]["pageProps"]["view"]["tabs"]
                for tab in tabs:
                    for content in tab.get("content", []):
                        if content.get("type") == "list":
                            list_title = content.get("title", "Unknown List")
                            uri = content.get("source", {}).get("uri")
                            if not uri:
                                continue
                                
                            separator = "&" if "?" in uri else "?"
                            api_uri = f"{uri}{separator}app_id={frontend_app_id}&app_key={frontend_app_key}"
                            
                            try:
                                api_resp = await client.get(api_uri, headers=headers)
                                api_resp.raise_for_status()
                                api_data = api_resp.json().get("data", [])
                                
                                programs = []
                                for item in api_data:
                                    if item.get("type") != "card": continue
                                    
                                    title = item.get("title", "")
                                    desc = item.get("description", "")
                                    
                                    item_id = None
                                    item_type = "program" # Default
                                    
                                    pointer = item.get("pointer", {})
                                    if pointer:
                                        item_type = pointer.get("type", "program")
                                        uri_val = pointer.get("uri", "")
                                        if "items/" in uri_val:
                                            item_id = uri_val.split("items/")[-1]
                                    
                                    published_at = None
                                    expires_at = None
                                    
                                    labels = item.get("labels", [])
                                    for label in labels:
                                        if not item_id and label.get("type") == "itemId":
                                            item_id = label.get("raw")
                                        
                                        if label.get("type") == "generic":
                                            fmt = label.get("formatted", "")
                                            # Look for "lisätty 1.3.2026" or "poistuu 1.3.2026"
                                            if "lisätty" in fmt:
                                                date_match = re.search(r"(\d+\.\d+\.\d+)", fmt)
                                                if date_match:
                                                    try:
                                                        published_at = datetime.strptime(date_match.group(1), "%d.%m.%Y").replace(tzinfo=timezone.utc)
                                                    except ValueError: pass
                                            elif "poistuu" in fmt:
                                                date_match = re.search(r"(\d+\.\d+\.\d+)", fmt)
                                                if date_match:
                                                    try:
                                                        expires_at = datetime.strptime(date_match.group(1), "%d.%m.%Y").replace(tzinfo=timezone.utc)
                                                    except ValueError: pass
                                    
                                    if not item_id:
                                        continue
                                        
                                    programs.append(Program(
                                        id=item_id,
                                        title=title,
                                        description=desc,
                                        type=item_type,
                                        url=f"https://areena.yle.fi/{item_id}",
                                        published_at=published_at,
                                        expires_at=expires_at
                                    ))
                                    
                                if programs:
                                    results[list_title] = programs
                                    
                            except Exception as e:
                                print(f"Error fetching list '{list_title}': {e}")
                                
            except KeyError as e:
                print(f"Failed to parse page structure: missing {e}")
                
            return results
