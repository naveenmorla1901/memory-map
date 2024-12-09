# apps/core/tests/test_sync.py
import pytest
from apps.core.services.sync_service import SyncService
from apps.core.services.firebase_service import FirebaseService

@pytest.fixture
def sync_service():
    """Provide SyncService instance"""
    return SyncService()

@pytest.mark.asyncio
class TestSyncService:
    async def test_conflict_resolution(self, sync_service):
        """Test sync conflict resolution logic"""
        try:
            # Create test data
            local_changes = {
                "name": "Local Update",
                "version": 1,
                "updated_at": "2024-01-01T00:00:00Z"
            }

            remote_changes = {
                "name": "Remote Update",
                "version": 2,
                "updated_at": "2024-01-02T00:00:00Z"
            }

            # Resolve conflict
            resolved = await sync_service.resolve_conflict(
                local_changes,
                remote_changes
            )

            # Remote should win (higher version)
            assert resolved["name"] == "Remote Update"
            assert resolved["version"] == 2

        except Exception as e:
            pytest.fail(f"Test failed: {str(e)}")