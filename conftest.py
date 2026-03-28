import pytest

# Enable asyncio mode for all async tests across the project
# Required for tests using @pytest.mark.asyncio
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )
