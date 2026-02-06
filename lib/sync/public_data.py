"""
Public Data Service.

This module provides a service for fetching public market sentiment data
from external APIs including Fear & Greed Index, funding rates, liquidations,
and open interest.

Requirements:
- 4.1: Fetch Fear_Greed_Index from Alternative.me API at configurable interval
- 4.2: Fetch funding rates from public Binance API for configured trading pairs
- 4.3: Fetch liquidation data from public CoinGlass API
- 4.4: Fetch open interest data from public APIs
- 4.5: Store data in MarketSentimentData model
- 4.6: Broadcast update via WebSocket_Broadcaster
- 4.7: Use cached data and display stale indicator if API is unavailable
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

import httpx

from apps.core.models import MarketSentimentData
from lib.messaging.websocket import WebSocketBroadcaster

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# API Endpoints
FEAR_GREED_API = "https://api.alternative.me/fng/"
BINANCE_FUNDING_RATE_API = "https://fapi.binance.com/fapi/v1/premiumIndex"
COINGLASS_LIQUIDATION_API = "https://open-api.coinglass.com/public/v2/liquidation_history"
BINANCE_OPEN_INTEREST_API = "https://fapi.binance.com/fapi/v1/openInterest"


class PublicDataService:
    """
    Service for fetching public market data.

    Fetches Fear & Greed Index, funding rates, liquidations,
    and open interest from public APIs.

    Requirements:
    - 4.1: Fetch Fear & Greed Index from Alternative.me
    - 4.2: Fetch funding rates from Binance
    - 4.3: Fetch liquidation data from CoinGlass
    - 4.4: Fetch open interest data
    - 4.5: Store in MarketSentimentData model
    - 4.6: Broadcast via WebSocket
    - 4.7: Handle API failures with cached data
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        broadcaster: WebSocketBroadcaster | None = None,
    ) -> None:
        """
        Initialize with optional dependencies.

        Args:
            http_client: Optional httpx AsyncClient for making HTTP requests
            broadcaster: Optional WebSocket broadcaster for real-time updates
        """
        self._http_client = http_client
        self.broadcaster = broadcaster or WebSocketBroadcaster()

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def fetch_fear_greed_index(self) -> dict[str, int | str] | None:
        """
        Fetch Fear & Greed Index from Alternative.me.

        Returns:
            Dict with 'value' (0-100) and 'classification' keys, or None if fetch failed

        Requirements:
        - 4.1: Fetch Fear & Greed Index from Alternative.me API
        """
        try:
            client = await self._get_http_client()
            response = await client.get(FEAR_GREED_API, params={"limit": 1})
            response.raise_for_status()

            data = response.json()
            if data and "data" in data and len(data["data"]) > 0:
                fng_data = data["data"][0]
                value = int(fng_data["value"])
                classification = fng_data["value_classification"]

                logger.info(f"Fetched Fear & Greed Index: {value} ({classification})")

                return {
                    "value": value,
                    "classification": classification,
                }

            logger.warning("Fear & Greed Index API returned empty data")
            return None

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching Fear & Greed Index: {e.response.status_code}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Request error fetching Fear & Greed Index: {e}")
            return None
        except (KeyError, ValueError, IndexError) as e:
            logger.error(f"Error parsing Fear & Greed Index response: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error fetching Fear & Greed Index: {e}")
            return None

    async def fetch_funding_rates(
        self,
        symbols: list[str],
    ) -> dict[str, dict[str, float | int]]:
        """
        Fetch funding rates from Binance for given symbols.

        Args:
            symbols: List of trading pair symbols (e.g., ['BTCUSDT', 'ETHUSDT'])

        Returns:
            Dict mapping symbol to funding rate data

        Requirements:
        - 4.2: Fetch funding rates from public Binance API
        """
        funding_rates: dict[str, dict[str, float | int]] = {}

        try:
            client = await self._get_http_client()

            for symbol in symbols:
                try:
                    # Convert symbol format (BTC_USDT -> BTCUSDT)
                    binance_symbol = symbol.replace("_", "")

                    response = await client.get(
                        BINANCE_FUNDING_RATE_API,
                        params={"symbol": binance_symbol},
                    )
                    response.raise_for_status()

                    data = response.json()
                    if data:
                        funding_rate = float(data.get("lastFundingRate", 0))
                        next_funding_time = data.get("nextFundingTime", 0)

                        funding_rates[symbol] = {
                            "rate": funding_rate,
                            "rate_percent": funding_rate * 100,
                            "next_funding_time": next_funding_time,
                        }

                        logger.debug(
                            f"Fetched funding rate for {symbol}: {funding_rate * 100:.4f}%"
                        )

                except httpx.HTTPStatusError as e:
                    logger.warning(
                        f"HTTP error fetching funding rate for {symbol}: {e.response.status_code}"
                    )
                    continue
                except Exception as e:
                    logger.warning(f"Error fetching funding rate for {symbol}: {e}")
                    continue

            logger.info(f"Fetched funding rates for {len(funding_rates)} symbols")

        except Exception as e:
            logger.exception(f"Unexpected error fetching funding rates: {e}")

        return funding_rates

    async def fetch_liquidations(self) -> dict[str, Decimal | float] | None:
        """
        Fetch recent liquidation data from CoinGlass.

        Note: CoinGlass API requires authentication for most endpoints.
        This implementation uses a fallback approach or mock data.

        Returns:
            Dict with liquidation data or None if fetch failed

        Requirements:
        - 4.3: Fetch liquidation data from public CoinGlass API
        """
        try:
            # Note: CoinGlass API typically requires API key for detailed data
            # For now, we'll return None and rely on cached data
            # In production, you would need to configure CoinGlass API key

            logger.warning(
                "CoinGlass API requires authentication. "
                "Liquidation data not available without API key."
            )
            return None

        except Exception as e:
            logger.exception(f"Unexpected error fetching liquidations: {e}")
            return None

    async def fetch_open_interest(
        self,
        symbols: list[str],
    ) -> dict[str, dict[str, float | str]]:
        """
        Fetch open interest data for given symbols.

        Args:
            symbols: List of trading pair symbols

        Returns:
            Dict mapping symbol to open interest data

        Requirements:
        - 4.4: Fetch open interest data from public APIs
        """
        open_interest_data: dict[str, dict[str, float | str]] = {}

        try:
            client = await self._get_http_client()

            for symbol in symbols:
                try:
                    # Convert symbol format (BTC_USDT -> BTCUSDT)
                    binance_symbol = symbol.replace("_", "")

                    response = await client.get(
                        BINANCE_OPEN_INTEREST_API,
                        params={"symbol": binance_symbol},
                    )
                    response.raise_for_status()

                    data = response.json()
                    if data:
                        open_interest = float(data.get("openInterest", 0))

                        open_interest_data[symbol] = {
                            "value": open_interest,
                            "symbol": symbol,
                        }

                        logger.debug(f"Fetched open interest for {symbol}: {open_interest}")

                except httpx.HTTPStatusError as e:
                    logger.warning(
                        f"HTTP error fetching open interest for {symbol}: {e.response.status_code}"
                    )
                    continue
                except Exception as e:
                    logger.warning(f"Error fetching open interest for {symbol}: {e}")
                    continue

            logger.info(f"Fetched open interest for {len(open_interest_data)} symbols")

        except Exception as e:
            logger.exception(f"Unexpected error fetching open interest: {e}")

        return open_interest_data

    async def fetch_all_public_data(
        self,
        symbols: list[str] | None = None,
    ) -> MarketSentimentData:
        """
        Fetch all public market data and create a record.

        This method:
        1. Fetches Fear & Greed Index
        2. Fetches funding rates for configured symbols
        3. Fetches liquidation data
        4. Fetches open interest data
        5. Creates a MarketSentimentData record
        6. Broadcasts the update via WebSocket

        Args:
            symbols: List of trading pair symbols to fetch data for.
                    Defaults to ['BTC_USDT', 'ETH_USDT'] if not provided.

        Returns:
            MarketSentimentData with all fetched data

        Requirements:
        - 4.1: Fetch Fear & Greed Index
        - 4.2: Fetch funding rates
        - 4.3: Fetch liquidation data
        - 4.4: Fetch open interest
        - 4.5: Store in MarketSentimentData model
        - 4.6: Broadcast via WebSocket
        - 4.7: Use cached data if APIs fail
        """
        if symbols is None:
            symbols = ["BTC_USDT", "ETH_USDT"]

        # Track if any API failed
        any_api_failed = False

        # Fetch Fear & Greed Index
        fng_data = await self.fetch_fear_greed_index()
        if fng_data is None:
            any_api_failed = True
            # Try to get cached data
            cached = MarketSentimentData.get_latest()
            if cached:
                fng_value = cached.fear_greed_index
                fng_classification = cached.fear_greed_classification
                logger.info("Using cached Fear & Greed Index data")
            else:
                fng_value = None
                fng_classification = ""
        else:
            fng_value = int(fng_data["value"])
            fng_classification = str(fng_data["classification"])

        # Fetch funding rates
        funding_rates = await self.fetch_funding_rates(symbols)
        if not funding_rates:
            any_api_failed = True
            # Try to get cached data
            cached = MarketSentimentData.get_latest()
            if cached and cached.funding_rates:
                funding_rates = cached.funding_rates
                logger.info("Using cached funding rates data")

        # Fetch liquidations
        liquidation_data = await self.fetch_liquidations()
        if liquidation_data is None:
            any_api_failed = True
            # Try to get cached data
            cached = MarketSentimentData.get_latest()
            if cached:
                liquidation_volume = cached.liquidation_volume_24h
                liquidation_long_pct = cached.liquidation_long_percent
                liquidation_short_pct = cached.liquidation_short_percent
                logger.info("Using cached liquidation data")
            else:
                liquidation_volume = None
                liquidation_long_pct = None
                liquidation_short_pct = None
        else:
            liquidation_volume = liquidation_data.get("volume_24h")  # type: ignore[assignment]
            liquidation_long_pct = liquidation_data.get("long_percent")  # type: ignore[assignment]
            liquidation_short_pct = liquidation_data.get("short_percent")  # type: ignore[assignment]

        # Fetch open interest
        open_interest = await self.fetch_open_interest(symbols)
        if not open_interest:
            any_api_failed = True
            # Try to get cached data
            cached = MarketSentimentData.get_latest()
            if cached and cached.open_interest:
                open_interest = cached.open_interest
                logger.info("Using cached open interest data")

        # Calculate BTC dominance (placeholder - would need additional API)
        btc_dominance = None

        # Create MarketSentimentData record
        sentiment_data = MarketSentimentData.objects.create(
            fear_greed_index=fng_value,
            fear_greed_classification=fng_classification,
            funding_rates=funding_rates,
            liquidation_volume_24h=liquidation_volume,
            liquidation_long_percent=liquidation_long_pct,
            liquidation_short_percent=liquidation_short_pct,
            open_interest=open_interest,
            btc_dominance=btc_dominance,
            is_stale=any_api_failed,
        )

        logger.info(
            f"Created market sentiment data record: FGI={fng_value}, stale={any_api_failed}"
        )

        # Broadcast update via WebSocket
        if fng_value is not None:
            await self.broadcaster.broadcast_sentiment_update(
                fear_greed_index=fng_value,
                signal=self._get_sentiment_signal(fng_value),
                classification=fng_classification,
            )

        return sentiment_data

    def _get_sentiment_signal(self, fear_greed_index: int) -> str:
        """
        Convert Fear & Greed Index to trading signal.

        Args:
            fear_greed_index: Fear & Greed Index value (0-100)

        Returns:
            Trading signal: BUY, SELL, or HOLD
        """
        if fear_greed_index <= 25:
            return "BUY"  # Extreme Fear - potential buying opportunity
        elif fear_greed_index >= 75:
            return "SELL"  # Extreme Greed - potential selling opportunity
        else:
            return "HOLD"  # Neutral

    async def close(self) -> None:
        """Close the HTTP client if it was created by this service."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None
