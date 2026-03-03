import pytest

# Wymagane przez pytest-asyncio >= 0.21: tryb "auto" pozwala na używanie
# dekoratora @pytest.mark.asyncio bez dodatkowych ustawień w każdym pliku.
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "asyncio: zaznacza test jako asynchroniczny (pytest-asyncio)"
    )
