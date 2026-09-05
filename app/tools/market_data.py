from typing import Optional

import httpx
from pydantic import BaseModel
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

YAHOO_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"


class MarketQuote(BaseModel):
    ticker: str
    regular_market_price: Optional[float] = None
    regular_market_volume: Optional[float] = None
    market_cap: Optional[float] = None
    trailing_pe: Optional[float] = None


class MarketDataClient:
    """Async Yahoo Finance quote client with retries for 429/timeouts."""

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
        reraise=True,
    )
    async def fetch_quote(self, ticker: str) -> MarketQuote:
        symbol = ticker.upper().strip()
        async with httpx.AsyncClient(
            headers=self.headers,
            timeout=self.timeout,
            follow_redirects=True,
        ) as client:
            response = await client.get(YAHOO_QUOTE_URL, params={"symbols": symbol})
            response.raise_for_status()
            payload = response.json()

        results = (payload.get("quoteResponse") or {}).get("result") or []
        if not results:
            raise ValueError(f"Yahoo Finance returned no quote for {symbol}.")

        row = results[0]
        return MarketQuote(
            ticker=symbol,
            regular_market_price=_as_float(row.get("regularMarketPrice")),
            regular_market_volume=_as_float(row.get("regularMarketVolume")),
            market_cap=_as_float(row.get("marketCap")),
            trailing_pe=_as_float(row.get("trailingPE")),
        )


def _as_float(value: object) -> Optional[float]:
    if value is None:
        return None
    return float(value)
