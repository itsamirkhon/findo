from __future__ import annotations

import logging
import time

import httpx

log = logging.getLogger(__name__)

# URL template for free exchange rate API
API_URL = "https://open.er-api.com/v6/latest/{base}"

# In-memory cache for exchange rates
# Format: { "BASE_CURRENCY": {"timestamp": float, "rates": dict} }
_cache: dict[str, dict] = {}
CACHE_TTL_SECONDS = 3600 * 12  # 12 hours


async def get_exchange_rate(from_currency: str, to_currency: str) -> float:
    """
    Get the exchange rate from a specific currency to another currency.
    If they are the same, returns 1.0.
    """
    from_currency = from_currency.strip().upper()
    to_currency = to_currency.strip().upper()

    if from_currency == to_currency:
        return 1.0

    now = time.time()
    
    # Check cache first
    cached_data = _cache.get(from_currency)
    if cached_data and (now - cached_data["timestamp"] < CACHE_TTL_SECONDS):
        rates = cached_data["rates"]
        if to_currency in rates:
            return float(rates[to_currency])

    # Fetch from API
    url = API_URL.format(base=from_currency)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        if data.get("result") == "success":
            rates = data.get("rates", {})
            _cache[from_currency] = {
                "timestamp": now,
                "rates": rates
            }
            if to_currency in rates:
                return float(rates[to_currency])
            else:
                log.warning(f"Target currency {to_currency} not found in rates for {from_currency}.")
        else:
            log.error(f"Failed to fetch rates for {from_currency}: {data}")

    except Exception as exc:
        log.exception(f"Exception fetching exchange rates for {from_currency}: {exc}")

    # Fallback: if API fails or currency not found, return 1.0 to avoid breaking functionality
    # You could also raise an error, but returning 1.0 allows the expense to be added
    # rather than dropping the transaction entirely.
    log.warning(f"Falling back to 1:1 rate for {from_currency} -> {to_currency}")
    return 1.0


async def convert_amount(amount: float, from_currency: str, to_currency: str) -> float:
    """
    Helper function to convert an amount from one currency to another.
    """
    rate = await get_exchange_rate(from_currency, to_currency)
    return float(amount) * rate
