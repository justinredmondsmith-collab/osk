"""Pytest configuration for browser tests."""

import pytest


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--cycles",
        action="store",
        default=100,
        type=int,
        help="Number of reconnect cycles for stress test",
    )


@pytest.fixture
def cycles(request):
    """Get the number of cycles from command line."""
    return request.config.getoption("--cycles")
