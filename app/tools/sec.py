import os
import asyncio
from typing import Dict, List, Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.api.schemas.reports import RawMetric

SEC_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


class SECClient:
    def __init__(self, user_agent: Optional[str] = None):
        self.user_agent = user_agent or os.getenv(
            "SEC_EDGAR_USER_AGENT", "QuantAnalyst ResearchBot admin@example.com"
        )
        self.headers = {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Host": "data.sec.gov",
        }
        self._ticker_to_cik: Dict[str, str] = {}

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    )
    async def _get_cik_for_ticker(self, ticker: str) -> str:
        ticker = ticker.upper().strip()
        if self._ticker_to_cik:
            cik = self._ticker_to_cik.get(ticker)
            if not cik:
                raise ValueError(f"Ticker {ticker} not found in SEC database.")
            return cik

        async with httpx.AsyncClient() as client:
            headers = {"User-Agent": self.user_agent}
            resp = await client.get(SEC_TICKERS_URL, headers=headers, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()

            for item in data.values():
                cik_padded = str(item["cik_str"]).zfill(10)
                self._ticker_to_cik[item["ticker"].upper()] = cik_padded

        cik = self._ticker_to_cik.get(ticker)
        if not cik:
            raise ValueError(f"Ticker {ticker} not found in SEC database.")
        return cik

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    )
    async def fetch_company_facts(self, ticker: str) -> Dict:
        cik = await self._get_cik_for_ticker(ticker)
        url = SEC_COMPANY_FACTS_URL.format(cik=cik)

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self.headers, timeout=15.0)
            if resp.status_code == 429:
                await asyncio.sleep(2.0)
            resp.raise_for_status()
            return resp.json()

    async def get_quarterly_financials(
        self, ticker: str, periods_count: int = 4
    ) -> List[RawMetric]:
        """
        Retrieves recent quarterly facts: Revenue, Gross Profit, Operating Income, Net Income.
        """
        facts = await self.fetch_company_facts(ticker)
        us_gaap = facts.get("facts", {}).get("us-gaap", {})
        raw_metrics: List[RawMetric] = []

        concept_map = {
            "Revenues": "Revenue",
            "RevenueFromContractWithCustomerExcludingAssessedTax": "Revenue",
            "GrossProfit": "GrossProfit",
            "OperatingIncomeLoss": "OperatingIncome",
            "NetIncomeLoss": "NetIncome",
        }

        for sec_concept, standard_name in concept_map.items():
            if sec_concept in us_gaap:
                units = us_gaap[sec_concept].get("units", {}).get("USD", [])
                # Filter for quarterly 10-Q filings with form 10-Q
                quarterly_units = [
                    u for u in units if u.get("form") in ["10-Q", "10-K"] and "frame" in u
                ]
                quarterly_units.sort(key=lambda x: x.get("end", ""), reverse=True)

                for u in quarterly_units[:periods_count]:
                    raw_metrics.append(
                        RawMetric(
                            name=standard_name,
                            period=u.get("frame", u.get("end")),
                            value=float(u.get("val", 0.0)),
                            unit="USD",
                            source_filing=f"{u.get('form')} ({u.get('end')})",
                            accession_number=u.get("accn"),
                            confidence=1.0,
                        )
                    )

        return raw_metrics 