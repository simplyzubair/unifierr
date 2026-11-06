import pytest
import respx


@pytest.fixture
def mock():
    with respx.mock(assert_all_called=False) as m:
        yield m
