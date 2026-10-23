import asyncio
import httpx


class TMDbUnavailable(Exception):
    """Raised when TMDb can't be reached (network/timeout) after retrying, as opposed to a clean 'no results'."""


class TMDbClient:
    _TIMEOUT = httpx.Timeout(15.0, connect=10.0)
    _RETRYABLE_STATUS = {429, 500, 502, 503, 504}

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.themoviedb.org/3"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "accept": "application/json"
        }

    @staticmethod
    def _extract_year(result: dict, media_type: str) -> int | None:
        date_key = "first_air_date" if media_type == "series" else "release_date"
        date_val = result.get(date_key)
        if isinstance(date_val, str) and len(date_val) >= 4 and date_val[:4].isdigit():
            return int(date_val[:4])
        return None

    async def _get(self, client: httpx.AsyncClient, url: str, params: dict) -> httpx.Response:
        """GET with one retry on transient network/timeout errors or 429/5xx; raises TMDbUnavailable if both attempts fail.

        A genuine 4xx (401, 404, ...) is returned as-is on the first attempt so callers can
        distinguish "invalid key" / "not found" from "TMDb is temporarily struggling".
        """
        for attempt in (1, 2):
            try:
                response = await client.get(url, headers=self.headers, params=params)
            except httpx.RequestError as e:
                if attempt == 2:
                    raise TMDbUnavailable(f"TMDb request failed after retry: {e}") from e
                await asyncio.sleep(0.5)
                continue

            if response.status_code in self._RETRYABLE_STATUS:
                if attempt == 2:
                    raise TMDbUnavailable(f"TMDb returned {response.status_code} after retry")
                await asyncio.sleep(0.5)
                continue

            return response

    async def get_match(self, title: str, year: int | None = None, media_type: str = "program") -> dict | None:
        """Searches TMDb and returns best match metadata (rating, year, title, id).

        Returns None only for a genuine no-results search. Raises TMDbUnavailable if
        TMDb couldn't be reached at all, so callers can tell "not found" from "network broke".
        """
        tmdb_type = "tv" if media_type == "series" else "movie"
        url = f"{self.base_url}/search/{tmdb_type}"

        params = {
            "query": title,
            "language": "fi-FI",
            "page": 1,
            "include_adult": "true"
        }
        if year:
            if tmdb_type == "movie":
                params["primary_release_year"] = year
            else:
                params["first_air_date_year"] = year

        try:
            async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
                response = await self._get(client, url, params)
                response.raise_for_status()
                data = response.json()
                results = data.get("results", [])
                if not results:
                    tmdb_type = "movie" if tmdb_type == "tv" else "tv"
                    fallback_url = f"{self.base_url}/search/{tmdb_type}"
                    response = await self._get(client, fallback_url, {"query": title, "language": "fi-FI", "page": 1, "include_adult": "true"})
                    response.raise_for_status()
                    data = response.json()
                    results = data.get("results", [])

                if not results:
                    return None

                best_match = results[0]
                rating = best_match.get("vote_average")
                matched_media_type = "series" if tmdb_type == "tv" else "program"
                out_year = self._extract_year(best_match, matched_media_type)
                return {
                    "tmdb_id": best_match.get("id"),
                    "title": best_match.get("title") or best_match.get("name"),
                    "rating": float(rating) if rating is not None and rating > 0 else None,
                    "year": out_year,
                    "media_type": matched_media_type
                }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                print("TMDb API Error: Invalid API key. Ratings/year lookup skipped.")
            return None

    async def get_rating(self, title: str, year: int | None = None, media_type: str = "program") -> float | None:
        match = await self.get_match(title=title, year=year, media_type=media_type)
        return match.get("rating") if match else None

    async def get_details(self, tmdb_id: int, media_type: str = "program") -> dict | None:
        """Fetches full detail (overview, genres, runtime, cast) for a known TMDb id.

        Returns None only for a genuine 404 (id doesn't exist for either type). Raises
        TMDbUnavailable if TMDb couldn't be reached at all.
        """
        tmdb_type = "tv" if media_type == "series" else "movie"
        url = f"{self.base_url}/{tmdb_type}/{tmdb_id}"
        params = {"language": "fi-FI", "append_to_response": "credits,keywords"}

        async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
            try:
                response = await self._get(client, url, params)
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    print("TMDb API Error: Invalid API key. Details lookup skipped.")
                    return None
                if e.response.status_code != 404:
                    return None
                # Wrong id/type pairing (movie id looked up as tv, or vice versa); retry once.
                tmdb_type = "movie" if tmdb_type == "tv" else "tv"
                fallback_url = f"{self.base_url}/{tmdb_type}/{tmdb_id}"
                try:
                    response = await self._get(client, fallback_url, params)
                    response.raise_for_status()
                    data = response.json()
                except httpx.HTTPStatusError:
                    return None

        credits = data.get("credits", {})
        cast = [c.get("name") for c in credits.get("cast", [])[:8] if c.get("name")]
        directors = [c.get("name") for c in credits.get("crew", []) if c.get("job") == "Director"]
        genres = [g.get("name") for g in data.get("genres", []) if g.get("name")]
        keywords_block = data.get("keywords", {})
        keywords = [k.get("name") for k in keywords_block.get("keywords", keywords_block.get("results", [])) if k.get("name")]

        return {
            "tmdb_id": data.get("id"),
            "media_type": "series" if tmdb_type == "tv" else "program",
            "title": data.get("title") or data.get("name"),
            "original_title": data.get("original_title") or data.get("original_name"),
            "tagline": data.get("tagline") or None,
            "overview": data.get("overview") or None,
            "year": self._extract_year(data, "series" if tmdb_type == "tv" else "program"),
            "genres": genres,
            "runtime_minutes": data.get("runtime") or (data.get("episode_run_time") or [None])[0],
            "vote_average": data.get("vote_average"),
            "vote_count": data.get("vote_count"),
            "popularity": data.get("popularity"),
            "original_language": data.get("original_language"),
            "cast": cast,
            "directors": directors,
            "keywords": keywords,
        }

    async def search_details(self, title: str, year: int | None = None, media_type: str = "program") -> dict | None:
        """Convenience: search for the best match, then fetch its full details in one call."""
        match = await self.get_match(title, year=year, media_type=media_type)
        if not match or not match.get("tmdb_id"):
            return None
        return await self.get_details(match["tmdb_id"], media_type=match["media_type"])
