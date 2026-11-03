"""Standard library and third-party imports, plus one shadowed stdlib name."""

from __future__ import annotations

import os.path
import queue
import sys
import xml.etree.ElementTree as ElementTree
from collections.abc import Mapping

import requests
from flask import Flask
from sqlalchemy.orm import Session

from pkg.client import ApiClient

APP = Flask(__name__)
PENDING = queue.JobQueue()


def health(session: Session) -> Mapping[str, object]:
    """Report where the service runs and whether the upstream answers."""
    reply = requests.get("https://example.invalid/health", timeout=5)
    document = ElementTree.fromstring(reply.text)
    return {
        "root": os.path.dirname(sys.argv[0]),
        "status": document.tag,
        "upstream": ApiClient().post({"ping": True}),
        "session": session.bind is not None,
    }
