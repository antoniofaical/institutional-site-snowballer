"""Unit tests use simulated HTTP and never contact public sites."""

import socket

import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Network disabled: use simulated HTTP")

    monkeypatch.setattr(socket.socket, "connect", blocked)
