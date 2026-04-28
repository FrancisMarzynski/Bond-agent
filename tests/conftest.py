import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


# Wymagane przez pytest-asyncio >= 0.21: tryb "auto" pozwala na używanie
# dekoratora @pytest.mark.asyncio bez dodatkowych ustawień w każdym pliku.
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "asyncio: zaznacza test jako asynchroniczny (pytest-asyncio)"
    )
