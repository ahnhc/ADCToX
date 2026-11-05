"""A fixed ADCTOX_PORT must be taken by one process only: on Windows SO_REUSEADDR lets a second one bind the same port."""
from http.server import BaseHTTPRequestHandler
import pathlib, sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ml"))
import webapp


def test_a_second_server_cannot_bind_a_port_that_is_serving():
    first = webapp._Server(("127.0.0.1", 0), BaseHTTPRequestHandler)
    try:
        with pytest.raises(OSError):
            webapp._Server(("127.0.0.1", first.server_port), BaseHTTPRequestHandler).server_close()
    finally:
        first.server_close()
