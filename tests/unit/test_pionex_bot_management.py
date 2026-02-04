"""
Unit tests for Pionex API Client Bot Management Methods.

Tests the PionexClient class for:
- list_bots(): Retrieve all active bots
- create_grid_bot(): Create a new Grid trading bot
- create_dca_bot(): Create a new DCA bot
- stop_bot(): Stop an active bot
- get_bot_details(): Get details of a specific bot

Requirements:
- 10.1: Retrieve all active bots (Grid, DCA, Infinity Grid, Futures Grid)
- 10.2: Retrieve bot type, trading pair, status, invested amount, current P&L
- 10.3: Create a new Grid Bot with calculated price range and grid count
- 10.4: Create a new DCA Bot with calculated investment intervals
- 10.5: Stop the bot and realize current positions
- 10.6: Close all open orders and return funds to available balance
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lib.pionex.client import PionexClient
from lib.pionex.models import (
    BotInfo,
    BotStatus,
    BotType,
    DCABotParams,
    GridBotParams,
    PionexAPIError,
)


# Sample API responses for mocking
SAMPLE_LIST_BOTS_RESPONSE = {
    "result": True,
    "data": {
        "bots": [
            {
                "botId": "grid_bot_001",
                "botType": "GRID",
                "symbol": "BTC_USDT",
                "status": "ACTIVE",
                "invested": "1000.00",
                "currentValue": "1050.00",
                "pnl": "50.00",
                "pnlPercent": 5.0,
                "lowerPrice": "30000.00",
                "upperPrice": "40000.00",
                "gridCount": 10,
                "createdAt": 1700000000000,
            },
            {
                "botId": "dca_bot_001",
                "botType": "DCA",
                "symbol": "ETH_USDT",
                "status": "ACTIVE",
                "invested": "500.00",
                "currentValue": "520.00",
                "pnl": "20.00",
                "pnlPercent": 4.0,
                "investmentPerOrder": "100.00",
                "intervalHours": 24,
                "totalInvestment": "1000.00",
                "createdAt": 1700000001000,
            },
        ]
    },
}

SAMPLE_LIST_BOTS_GROUPED_RESPONSE = {
    "result": True,
    "data": {
        "gridBots": [
            {
                "botId": "grid_bot_002",
                "botType": "GRID",
                "symbol": "SOL_USDT",
                "status": "ACTIVE",
                "invested": "200.00",
                "currentValue": "210.00",
                "pnl": "10.00",
                "pnlPercent": 5.0,
            },
        ],
        "dcaBots": [
            {
                "botId": "dca_bot_002",
                "botType": "DCA",
                "symbol": "DOGE_USDT",
                "status": "STOPPED",
                "invested": "100.00",
                "currentValue": "95.00",
                "pnl": "-5.00",
                "pnlPercent": -5.0,
            },
        ],
        "infinityGridBots": [],
        "futuresGridBots": [],
    },
}

SAMPLE_CREATE_GRID_BOT_RESPONSE = {
    "result": True,
    "data": {
        "botId": "grid_bot_new_001",
        "botType": "GRID",
        "symbol": "BTC_USDT",
        "status": "CREATING",
        "invested": "1000.00",
        "currentValue": "1000.00",
        "pnl": "0",
        "pnlPercent": 0.0,
        "lowerPrice": "30000.00",
        "upperPrice": "40000.00",
        "gridCount": 10,
        "createdAt": 1700000002000,
    },
}

SAMPLE_CREATE_DCA_BOT_RESPONSE = {
    "result": True,
    "data": {
        "botId": "dca_bot_new_001",
        "botType": "DCA",
        "symbol": "ETH_USDT",
        "status": "ACTIVE",
        "invested": "100.00",
        "currentValue": "100.00",
        "pnl": "0",
        "pnlPercent": 0.0,
        "investmentPerOrder": "100.00",
        "intervalHours": 24,
        "totalInvestment": "1000.00",
        "createdAt": 1700000003000,
    },
}

SAMPLE_STOP_BOT_RESPONSE = {
    "result": True,
    "data": {
        "success": True,
        "botId": "grid_bot_001",
    },
}

SAMPLE_GET_BOT_DETAILS_RESPONSE = {
    "result": True,
    "data": {
        "botId": "grid_bot_001",
        "botType": "GRID",
        "symbol": "BTC_USDT",
        "status": "ACTIVE",
        "invested": "1000.00",
        "currentValue": "1100.00",
        "pnl": "100.00",
        "pnlPercent": 10.0,
        "lowerPrice": "30000.00",
        "upperPrice": "40000.00",
        "gridCount": 10,
        "createdAt": 1700000000000,
    },
}


class TestGridBotParams:
    """Tests for GridBotParams model validation."""

    def test_valid_grid_bot_params(self) -> None:
        """Test valid GridBotParams creation."""
        params = GridBotParams(
            symbol="BTC_USDT",
            lower_price=30000.0,
            upper_price=40000.0,
            grid_count=10,
            investment=Decimal("1000.00"),
        )
        assert params.symbol == "BTC_USDT"
        assert params.lower_price == 30000.0
        assert params.upper_price == 40000.0
        assert params.grid_count == 10
        assert params.investment == Decimal("1000.00")

    def test_lower_price_must_be_positive(self) -> None:
        """Test lower price must be positive."""
        with pytest.raises(ValueError, match="Lower price must be positive"):
            GridBotParams(
                symbol="BTC_USDT",
                lower_price=0,
                upper_price=40000.0,
                grid_count=10,
                investment=Decimal("1000.00"),
            )

    def test_upper_price_must_be_positive(self) -> None:
        """Test upper price must be positive."""
        with pytest.raises(ValueError, match="Upper price must be positive"):
            GridBotParams(
                symbol="BTC_USDT",
                lower_price=30000.0,
                upper_price=0,
                grid_count=10,
                investment=Decimal("1000.00"),
            )

    def test_lower_must_be_less_than_upper(self) -> None:
        """Test lower price must be less than upper price."""
        with pytest.raises(ValueError, match="Lower price must be less than upper"):
            GridBotParams(
                symbol="BTC_USDT",
                lower_price=40000.0,
                upper_price=30000.0,
                grid_count=10,
                investment=Decimal("1000.00"),
            )

    def test_grid_count_minimum(self) -> None:
        """Test grid count must be at least 2."""
        with pytest.raises(ValueError, match="Grid count must be at least 2"):
            GridBotParams(
                symbol="BTC_USDT",
                lower_price=30000.0,
                upper_price=40000.0,
                grid_count=1,
                investment=Decimal("1000.00"),
            )

    def test_investment_must_be_positive(self) -> None:
        """Test investment must be positive."""
        with pytest.raises(ValueError, match="Investment must be positive"):
            GridBotParams(
                symbol="BTC_USDT",
                lower_price=30000.0,
                upper_price=40000.0,
                grid_count=10,
                investment=Decimal("0"),
            )

    def test_to_api_params(self) -> None:
        """Test to_api_params conversion."""
        params = GridBotParams(
            symbol="BTC_USDT",
            lower_price=30000.0,
            upper_price=40000.0,
            grid_count=10,
            investment=Decimal("1000.00"),
        )
        api_params = params.to_api_params()
        assert api_params["symbol"] == "BTC_USDT"
        assert api_params["lowerPrice"] == "30000.0"
        assert api_params["upperPrice"] == "40000.0"
        assert api_params["gridCount"] == 10
        assert api_params["investment"] == "1000.00"


class TestDCABotParams:
    """Tests for DCABotParams model validation."""

    def test_valid_dca_bot_params(self) -> None:
        """Test valid DCABotParams creation."""
        params = DCABotParams(
            symbol="ETH_USDT",
            investment_per_order=Decimal("100.00"),
            interval_hours=24,
            total_investment=Decimal("1000.00"),
        )
        assert params.symbol == "ETH_USDT"
        assert params.investment_per_order == Decimal("100.00")
        assert params.interval_hours == 24
        assert params.total_investment == Decimal("1000.00")

    def test_investment_per_order_must_be_positive(self) -> None:
        """Test investment per order must be positive."""
        with pytest.raises(ValueError, match="Investment per order must be positive"):
            DCABotParams(
                symbol="ETH_USDT",
                investment_per_order=Decimal("0"),
                interval_hours=24,
                total_investment=Decimal("1000.00"),
            )

    def test_interval_hours_minimum(self) -> None:
        """Test interval hours must be at least 1."""
        with pytest.raises(ValueError, match="Interval hours must be at least 1"):
            DCABotParams(
                symbol="ETH_USDT",
                investment_per_order=Decimal("100.00"),
                interval_hours=0,
                total_investment=Decimal("1000.00"),
            )

    def test_total_investment_must_be_positive(self) -> None:
        """Test total investment must be positive."""
        with pytest.raises(ValueError, match="Total investment must be positive"):
            DCABotParams(
                symbol="ETH_USDT",
                investment_per_order=Decimal("100.00"),
                interval_hours=24,
                total_investment=Decimal("0"),
            )

    def test_investment_per_order_cannot_exceed_total(self) -> None:
        """Test investment per order cannot exceed total investment."""
        with pytest.raises(ValueError, match="Investment per order cannot exceed"):
            DCABotParams(
                symbol="ETH_USDT",
                investment_per_order=Decimal("1500.00"),
                interval_hours=24,
                total_investment=Decimal("1000.00"),
            )

    def test_to_api_params(self) -> None:
        """Test to_api_params conversion."""
        params = DCABotParams(
            symbol="ETH_USDT",
            investment_per_order=Decimal("100.00"),
            interval_hours=24,
            total_investment=Decimal("1000.00"),
        )
        api_params = params.to_api_params()
        assert api_params["symbol"] == "ETH_USDT"
        assert api_params["investmentPerOrder"] == "100.00"
        assert api_params["intervalHours"] == 24
        assert api_params["totalInvestment"] == "1000.00"


class TestBotInfo:
    """Tests for BotInfo model parsing."""

    def test_from_api_response_grid_bot(self) -> None:
        """Test parsing Grid bot from API response."""
        data = {
            "botId": "grid_bot_001",
            "botType": "GRID",
            "symbol": "BTC_USDT",
            "status": "ACTIVE",
            "invested": "1000.00",
            "currentValue": "1050.00",
            "pnl": "50.00",
            "pnlPercent": 5.0,
            "lowerPrice": "30000.00",
            "upperPrice": "40000.00",
            "gridCount": 10,
            "createdAt": 1700000000000,
        }
        bot = BotInfo.from_api_response(data)
        
        assert bot.bot_id == "grid_bot_001"
        assert bot.bot_type == BotType.GRID
        assert bot.symbol == "BTC_USDT"
        assert bot.status == BotStatus.ACTIVE
        assert bot.invested == Decimal("1000.00")
        assert bot.current_value == Decimal("1050.00")
        assert bot.pnl == Decimal("50.00")
        assert bot.pnl_percent == 5.0
        assert bot.params is not None
        assert isinstance(bot.params, GridBotParams)
        assert bot.params.lower_price == 30000.0
        assert bot.params.upper_price == 40000.0
        assert bot.params.grid_count == 10

    def test_from_api_response_dca_bot(self) -> None:
        """Test parsing DCA bot from API response."""
        data = {
            "botId": "dca_bot_001",
            "botType": "DCA",
            "symbol": "ETH_USDT",
            "status": "ACTIVE",
            "invested": "500.00",
            "currentValue": "520.00",
            "pnl": "20.00",
            "pnlPercent": 4.0,
            "investmentPerOrder": "100.00",
            "intervalHours": 24,
            "totalInvestment": "1000.00",
        }
        bot = BotInfo.from_api_response(data)
        
        assert bot.bot_id == "dca_bot_001"
        assert bot.bot_type == BotType.DCA
        assert bot.symbol == "ETH_USDT"
        assert bot.status == BotStatus.ACTIVE
        assert bot.invested == Decimal("500.00")
        assert bot.pnl == Decimal("20.00")
        assert bot.params is not None
        assert isinstance(bot.params, DCABotParams)
        assert bot.params.investment_per_order == Decimal("100.00")
        assert bot.params.interval_hours == 24

    def test_from_api_response_stopped_bot(self) -> None:
        """Test parsing stopped bot from API response."""
        data = {
            "botId": "bot_stopped",
            "botType": "GRID",
            "symbol": "SOL_USDT",
            "status": "STOPPED",
            "invested": "200.00",
            "currentValue": "180.00",
            "pnl": "-20.00",
            "pnlPercent": -10.0,
        }
        bot = BotInfo.from_api_response(data)
        
        assert bot.status == BotStatus.STOPPED
        assert bot.pnl == Decimal("-20.00")
        assert bot.pnl_percent == -10.0

    def test_from_api_response_infinity_grid_bot(self) -> None:
        """Test parsing Infinity Grid bot from API response."""
        data = {
            "botId": "infinity_grid_001",
            "botType": "INFINITY_GRID",
            "symbol": "BTC_USDT",
            "status": "ACTIVE",
            "invested": "5000.00",
            "currentValue": "5500.00",
            "pnl": "500.00",
            "pnlPercent": 10.0,
        }
        bot = BotInfo.from_api_response(data)
        
        assert bot.bot_type == BotType.INFINITY_GRID

    def test_from_api_response_unknown_type_defaults_to_grid(self) -> None:
        """Test unknown bot type defaults to GRID."""
        data = {
            "botId": "unknown_bot",
            "botType": "UNKNOWN_TYPE",
            "symbol": "BTC_USDT",
            "status": "ACTIVE",
            "invested": "100.00",
        }
        bot = BotInfo.from_api_response(data)
        
        assert bot.bot_type == BotType.GRID


class TestListBots:
    """Tests for list_bots method.
    
    Requirements:
        - 10.1: Retrieve all active bots (Grid, DCA, Infinity Grid, Futures Grid)
        - 10.2: Retrieve bot type, trading pair, status, invested amount, current P&L
    """

    @pytest.mark.asyncio
    async def test_list_bots_returns_list(self) -> None:
        """Test list_bots returns list of BotInfo objects."""
        client = PionexClient(api_key="key", api_secret="secret")
        
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_LIST_BOTS_RESPONSE
        
        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client
            
            bots = await client.list_bots()
        
        assert isinstance(bots, list)
        assert len(bots) == 2
        assert all(isinstance(b, BotInfo) for b in bots)

    @pytest.mark.asyncio
    async def test_list_bots_parses_grid_bot(self) -> None:
        """Test Grid bot is parsed correctly."""
        client = PionexClient(api_key="key", api_secret="secret")
        
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_LIST_BOTS_RESPONSE
        
        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client
            
            bots = await client.list_bots()
        
        grid_bot = next(b for b in bots if b.bot_id == "grid_bot_001")
        assert grid_bot.bot_type == BotType.GRID
        assert grid_bot.symbol == "BTC_USDT"
        assert grid_bot.status == BotStatus.ACTIVE
        assert grid_bot.invested == Decimal("1000.00")
        assert grid_bot.pnl == Decimal("50.00")
        assert grid_bot.pnl_percent == 5.0

    @pytest.mark.asyncio
    async def test_list_bots_parses_dca_bot(self) -> None:
        """Test DCA bot is parsed correctly."""
        client = PionexClient(api_key="key", api_secret="secret")
        
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_LIST_BOTS_RESPONSE
        
        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client
            
            bots = await client.list_bots()
        
        dca_bot = next(b for b in bots if b.bot_id == "dca_bot_001")
        assert dca_bot.bot_type == BotType.DCA
        assert dca_bot.symbol == "ETH_USDT"

    @pytest.mark.asyncio
    async def test_list_bots_handles_grouped_response(self) -> None:
        """Test list_bots handles grouped bot response format."""
        client = PionexClient(api_key="key", api_secret="secret")
        
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_LIST_BOTS_GROUPED_RESPONSE
        
        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client
            
            bots = await client.list_bots()
        
        assert len(bots) == 2
        bot_ids = [b.bot_id for b in bots]
        assert "grid_bot_002" in bot_ids
        assert "dca_bot_002" in bot_ids

    @pytest.mark.asyncio
    async def test_list_bots_is_authenticated(self) -> None:
        """Test list_bots uses authenticated request."""
        client = PionexClient(api_key="key", api_secret="secret")
        
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = {"result": True, "data": {"bots": []}}
        
        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client
            
            await client.list_bots()
            
            call_args = mock_http_client.get.call_args
            headers = call_args.kwargs.get("headers", {})
            assert "PIONEX-KEY" in headers
            assert "PIONEX-SIGNATURE" in headers

    @pytest.mark.asyncio
    async def test_list_bots_empty_response(self) -> None:
        """Test list_bots handles empty bot list."""
        client = PionexClient(api_key="key", api_secret="secret")
        
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = {"result": True, "data": {"bots": []}}
        
        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client
            
            bots = await client.list_bots()
        
        assert bots == []


class TestCreateGridBot:
    """Tests for create_grid_bot method.
    
    Requirements:
        - 10.3: Create a new Grid Bot with calculated price range and grid count
    """

    @pytest.mark.asyncio
    async def test_create_grid_bot_returns_bot_info(self) -> None:
        """Test create_grid_bot returns BotInfo."""
        client = PionexClient(api_key="key", api_secret="secret")
        
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_CREATE_GRID_BOT_RESPONSE
        
        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client
            
            params = GridBotParams(
                symbol="BTC_USDT",
                lower_price=30000.0,
                upper_price=40000.0,
                grid_count=10,
                investment=Decimal("1000.00"),
            )
            bot = await client.create_grid_bot(params)
        
        assert isinstance(bot, BotInfo)
        assert bot.bot_id == "grid_bot_new_001"
        assert bot.bot_type == BotType.GRID
        assert bot.symbol == "BTC_USDT"

    @pytest.mark.asyncio
    async def test_create_grid_bot_sends_correct_params(self) -> None:
        """Test create_grid_bot sends correct parameters."""
        client = PionexClient(api_key="key", api_secret="secret")
        
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_CREATE_GRID_BOT_RESPONSE
        
        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client
            
            params = GridBotParams(
                symbol="BTC_USDT",
                lower_price=30000.0,
                upper_price=40000.0,
                grid_count=10,
                investment=Decimal("1000.00"),
            )
            await client.create_grid_bot(params)
            
            call_args = mock_http_client.post.call_args
            json_data = call_args.kwargs.get("json", {})
            assert json_data["symbol"] == "BTC_USDT"
            assert json_data["lowerPrice"] == "30000.0"
            assert json_data["upperPrice"] == "40000.0"
            assert json_data["gridCount"] == 10
            assert json_data["investment"] == "1000.00"

    @pytest.mark.asyncio
    async def test_create_grid_bot_is_authenticated(self) -> None:
        """Test create_grid_bot uses authenticated request."""
        client = PionexClient(api_key="key", api_secret="secret")
        
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_CREATE_GRID_BOT_RESPONSE
        
        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client
            
            params = GridBotParams(
                symbol="BTC_USDT",
                lower_price=30000.0,
                upper_price=40000.0,
                grid_count=10,
                investment=Decimal("1000.00"),
            )
            await client.create_grid_bot(params)
            
            call_args = mock_http_client.post.call_args
            headers = call_args.kwargs.get("headers", {})
            assert "PIONEX-KEY" in headers
            assert "PIONEX-SIGNATURE" in headers

    @pytest.mark.asyncio
    async def test_create_grid_bot_insufficient_balance_error(self) -> None:
        """Test create_grid_bot raises error on insufficient balance."""
        client = PionexClient(api_key="key", api_secret="secret")
        
        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 400
        mock_response.content = b'{"result": false}'
        mock_response.json.return_value = {
            "result": False,
            "code": 3001,
            "message": "Insufficient balance",
        }
        mock_response.headers = {}
        
        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client
            
            params = GridBotParams(
                symbol="BTC_USDT",
                lower_price=30000.0,
                upper_price=40000.0,
                grid_count=10,
                investment=Decimal("1000000.00"),
            )
            
            with pytest.raises(PionexAPIError) as exc_info:
                await client.create_grid_bot(params)
        
        assert "Insufficient balance" in exc_info.value.error.message


class TestCreateDCABot:
    """Tests for create_dca_bot method.
    
    Requirements:
        - 10.4: Create a new DCA Bot with calculated investment intervals
    """

    @pytest.mark.asyncio
    async def test_create_dca_bot_returns_bot_info(self) -> None:
        """Test create_dca_bot returns BotInfo."""
        client = PionexClient(api_key="key", api_secret="secret")
        
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_CREATE_DCA_BOT_RESPONSE
        
        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client
            
            params = DCABotParams(
                symbol="ETH_USDT",
                investment_per_order=Decimal("100.00"),
                interval_hours=24,
                total_investment=Decimal("1000.00"),
            )
            bot = await client.create_dca_bot(params)
        
        assert isinstance(bot, BotInfo)
        assert bot.bot_id == "dca_bot_new_001"
        assert bot.bot_type == BotType.DCA
        assert bot.symbol == "ETH_USDT"

    @pytest.mark.asyncio
    async def test_create_dca_bot_sends_correct_params(self) -> None:
        """Test create_dca_bot sends correct parameters."""
        client = PionexClient(api_key="key", api_secret="secret")
        
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_CREATE_DCA_BOT_RESPONSE
        
        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client
            
            params = DCABotParams(
                symbol="ETH_USDT",
                investment_per_order=Decimal("100.00"),
                interval_hours=24,
                total_investment=Decimal("1000.00"),
            )
            await client.create_dca_bot(params)
            
            call_args = mock_http_client.post.call_args
            json_data = call_args.kwargs.get("json", {})
            assert json_data["symbol"] == "ETH_USDT"
            assert json_data["investmentPerOrder"] == "100.00"
            assert json_data["intervalHours"] == 24
            assert json_data["totalInvestment"] == "1000.00"

    @pytest.mark.asyncio
    async def test_create_dca_bot_is_authenticated(self) -> None:
        """Test create_dca_bot uses authenticated request."""
        client = PionexClient(api_key="key", api_secret="secret")
        
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_CREATE_DCA_BOT_RESPONSE
        
        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client
            
            params = DCABotParams(
                symbol="ETH_USDT",
                investment_per_order=Decimal("100.00"),
                interval_hours=24,
                total_investment=Decimal("1000.00"),
            )
            await client.create_dca_bot(params)
            
            call_args = mock_http_client.post.call_args
            headers = call_args.kwargs.get("headers", {})
            assert "PIONEX-KEY" in headers
            assert "PIONEX-SIGNATURE" in headers


class TestStopBot:
    """Tests for stop_bot method.
    
    Requirements:
        - 10.5: Stop the bot and realize current positions
        - 10.6: Close all open orders and return funds to available balance
    """

    @pytest.mark.asyncio
    async def test_stop_bot_returns_true_on_success(self) -> None:
        """Test stop_bot returns True on success."""
        client = PionexClient(api_key="key", api_secret="secret")
        
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_STOP_BOT_RESPONSE
        
        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client
            
            result = await client.stop_bot("grid_bot_001")
        
        assert result is True

    @pytest.mark.asyncio
    async def test_stop_bot_sends_correct_params(self) -> None:
        """Test stop_bot sends correct parameters."""
        client = PionexClient(api_key="key", api_secret="secret")
        
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_STOP_BOT_RESPONSE
        
        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client
            
            await client.stop_bot("grid_bot_001")
            
            call_args = mock_http_client.post.call_args
            json_data = call_args.kwargs.get("json", {})
            assert json_data["botId"] == "grid_bot_001"

    @pytest.mark.asyncio
    async def test_stop_bot_is_authenticated(self) -> None:
        """Test stop_bot uses authenticated request."""
        client = PionexClient(api_key="key", api_secret="secret")
        
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_STOP_BOT_RESPONSE
        
        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client
            
            await client.stop_bot("grid_bot_001")
            
            call_args = mock_http_client.post.call_args
            headers = call_args.kwargs.get("headers", {})
            assert "PIONEX-KEY" in headers
            assert "PIONEX-SIGNATURE" in headers

    @pytest.mark.asyncio
    async def test_stop_bot_not_found_error(self) -> None:
        """Test stop_bot raises error when bot not found."""
        client = PionexClient(api_key="key", api_secret="secret")
        
        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 400
        mock_response.content = b'{"result": false}'
        mock_response.json.return_value = {
            "result": False,
            "code": 5001,
            "message": "Bot not found",
        }
        mock_response.headers = {}
        
        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client
            
            with pytest.raises(PionexAPIError) as exc_info:
                await client.stop_bot("nonexistent_bot")
        
        assert "Bot not found" in exc_info.value.error.message


class TestGetBotDetails:
    """Tests for get_bot_details method.
    
    Requirements:
        - 10.2: Retrieve bot type, trading pair, status, invested amount,
                current P&L, and configuration parameters
    """

    @pytest.mark.asyncio
    async def test_get_bot_details_returns_bot_info(self) -> None:
        """Test get_bot_details returns BotInfo."""
        client = PionexClient(api_key="key", api_secret="secret")
        
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_GET_BOT_DETAILS_RESPONSE
        
        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client
            
            bot = await client.get_bot_details("grid_bot_001")
        
        assert isinstance(bot, BotInfo)
        assert bot.bot_id == "grid_bot_001"
        assert bot.bot_type == BotType.GRID
        assert bot.symbol == "BTC_USDT"
        assert bot.status == BotStatus.ACTIVE
        assert bot.invested == Decimal("1000.00")
        assert bot.current_value == Decimal("1100.00")
        assert bot.pnl == Decimal("100.00")
        assert bot.pnl_percent == 10.0

    @pytest.mark.asyncio
    async def test_get_bot_details_sends_correct_params(self) -> None:
        """Test get_bot_details sends correct parameters."""
        client = PionexClient(api_key="key", api_secret="secret")
        
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_GET_BOT_DETAILS_RESPONSE
        
        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client
            
            await client.get_bot_details("grid_bot_001")
            
            call_args = mock_http_client.get.call_args
            params = call_args.kwargs.get("params", {})
            assert params["botId"] == "grid_bot_001"

    @pytest.mark.asyncio
    async def test_get_bot_details_is_authenticated(self) -> None:
        """Test get_bot_details uses authenticated request."""
        client = PionexClient(api_key="key", api_secret="secret")
        
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_GET_BOT_DETAILS_RESPONSE
        
        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client
            
            await client.get_bot_details("grid_bot_001")
            
            call_args = mock_http_client.get.call_args
            headers = call_args.kwargs.get("headers", {})
            assert "PIONEX-KEY" in headers
            assert "PIONEX-SIGNATURE" in headers

    @pytest.mark.asyncio
    async def test_get_bot_details_not_found_error(self) -> None:
        """Test get_bot_details raises error when bot not found."""
        client = PionexClient(api_key="key", api_secret="secret")
        
        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 400
        mock_response.content = b'{"result": false}'
        mock_response.json.return_value = {
            "result": False,
            "code": 5001,
            "message": "Bot not found",
        }
        mock_response.headers = {}
        
        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client
            
            with pytest.raises(PionexAPIError) as exc_info:
                await client.get_bot_details("nonexistent_bot")
        
        assert "Bot not found" in exc_info.value.error.message
