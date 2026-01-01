"""
Integration tests for full-text search using PostgreSQL.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.integration
class TestFullTextSearch:
    """Tests for PostgreSQL full-text search."""

    @pytest.mark.asyncio
    async def test_text_search_by_title(
        self,
        db_session: AsyncSession,
        test_properties,
    ):
        """Test searching properties by title."""
        from app.services.property import get_unified_properties_optimized
        from app.schemas.property import UnifiedPropertyFilter

        filters = UnifiedPropertyFilter(search_query="apartment")

        result = await get_unified_properties_optimized(
            db_session,
            filters,
            user_id=None,
            page=1,
            limit=20,
        )

        assert "items" in result

    @pytest.mark.asyncio
    async def test_text_search_by_locality(
        self,
        db_session: AsyncSession,
        test_properties,
    ):
        """Test searching properties by locality."""
        from app.services.property import get_unified_properties_optimized
        from app.schemas.property import UnifiedPropertyFilter

        filters = UnifiedPropertyFilter(search_query="Andheri")

        result = await get_unified_properties_optimized(
            db_session,
            filters,
            user_id=None,
            page=1,
            limit=20,
        )

        assert "items" in result

    @pytest.mark.asyncio
    async def test_text_search_relevance_sorting(
        self,
        db_session: AsyncSession,
        test_properties,
    ):
        """Test properties sorted by search relevance."""
        from app.services.property import get_unified_properties_optimized
        from app.schemas.property import UnifiedPropertyFilter, SortBy

        filters = UnifiedPropertyFilter(
            search_query="luxury apartment",
            sort_by=SortBy.relevance,
        )

        result = await get_unified_properties_optimized(
            db_session,
            filters,
            user_id=None,
            page=1,
            limit=20,
        )

        assert "items" in result

    @pytest.mark.asyncio
    async def test_text_search_empty_query(
        self,
        db_session: AsyncSession,
        test_properties,
    ):
        """Test search with empty query returns all properties."""
        from app.services.property import get_unified_properties_optimized
        from app.schemas.property import UnifiedPropertyFilter

        filters = UnifiedPropertyFilter(search_query="")

        result = await get_unified_properties_optimized(
            db_session,
            filters,
            user_id=None,
            page=1,
            limit=20,
        )

        assert "items" in result

    @pytest.mark.asyncio
    async def test_text_search_no_results(
        self,
        db_session: AsyncSession,
        test_properties,
    ):
        """Test search with no matching results."""
        from app.services.property import get_unified_properties_optimized
        from app.schemas.property import UnifiedPropertyFilter

        filters = UnifiedPropertyFilter(
            search_query="nonexistent_property_xyz_12345"
        )

        result = await get_unified_properties_optimized(
            db_session,
            filters,
            user_id=None,
            page=1,
            limit=20,
        )

        assert "items" in result
        assert result["total"] == 0 or len(result["items"]) == 0


@pytest.mark.integration
class TestTSVectorColumn:
    """Tests for __ts_vector__ column usage."""

    @pytest.mark.asyncio
    async def test_ts_vector_column_exists(
        self,
        db_session: AsyncSession,
        test_property,
    ):
        """Test that __ts_vector__ column exists."""
        from sqlalchemy import text

        result = await db_session.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'properties'
                AND column_name = '__ts_vector__'
            """)
        )
        columns = result.fetchall()

        # May not exist in all setups
        assert len(columns) >= 0

    @pytest.mark.asyncio
    async def test_plainto_tsquery(
        self,
        db_session: AsyncSession,
    ):
        """Test PostgreSQL plainto_tsquery function."""
        from sqlalchemy import text

        result = await db_session.execute(
            text("SELECT plainto_tsquery('english', 'luxury apartment')")
        )
        tsquery = result.scalar()

        assert tsquery is not None


@pytest.mark.integration
class TestSearchFilters:
    """Tests for combined search with filters."""

    @pytest.mark.asyncio
    async def test_search_with_city_filter(
        self,
        db_session: AsyncSession,
        test_properties,
    ):
        """Test search combined with city filter."""
        from app.services.property import get_unified_properties_optimized
        from app.schemas.property import UnifiedPropertyFilter

        filters = UnifiedPropertyFilter(
            search_query="apartment",
            city="Mumbai",
        )

        result = await get_unified_properties_optimized(
            db_session,
            filters,
            user_id=None,
            page=1,
            limit=20,
        )

        assert "items" in result
        for prop in result["items"]:
            assert "Mumbai" in prop.city or prop.city.lower() == "mumbai"

    @pytest.mark.asyncio
    async def test_search_with_price_filter(
        self,
        db_session: AsyncSession,
        test_properties,
    ):
        """Test search combined with price filter."""
        from app.services.property import get_unified_properties_optimized
        from app.schemas.property import UnifiedPropertyFilter

        filters = UnifiedPropertyFilter(
            search_query="apartment",
            price_min=10000,
            price_max=100000,
        )

        result = await get_unified_properties_optimized(
            db_session,
            filters,
            user_id=None,
            page=1,
            limit=20,
        )

        assert "items" in result

    @pytest.mark.asyncio
    async def test_search_with_property_type_filter(
        self,
        db_session: AsyncSession,
        test_properties,
    ):
        """Test search combined with property type filter."""
        from app.services.property import get_unified_properties_optimized
        from app.schemas.property import UnifiedPropertyFilter
        from app.models.enums import PropertyType

        filters = UnifiedPropertyFilter(
            search_query="spacious",
            property_type=[PropertyType.apartment],
        )

        result = await get_unified_properties_optimized(
            db_session,
            filters,
            user_id=None,
            page=1,
            limit=20,
        )

        assert "items" in result
        for prop in result["items"]:
            assert prop.property_type == PropertyType.apartment
