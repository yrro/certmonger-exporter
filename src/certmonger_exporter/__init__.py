#!/usr/bin/python3

import logging
import os
import signal
import select
import socket
import sys

from prometheus_client.core import REGISTRY
from systemd.daemon import notify
from systemd.journal import JournalHandler

from .collector import CertmongerCollector
from .prometheus_client import start_httpd_server


logger = logging.getLogger(__name__)


def main(argv):

    xr, xw = os.pipe()
    def sigterm(signum, frame):
        notify("STOPPING=1")
        os.write(xw, b'\0')

    signal.signal(signal.SIGTERM, sigterm)
    collector = CertmongerCollector()
    REGISTRY.register(collector)
    server, thread = start_httpd_server(int(os.environ.get("CERTMONGER_EXPORTER_PORT", "9630")), registry=REGISTRY)
    try:
        notify("READY=1")

        while True:
            rlist, _, _ = select.select([xr], [], [])

            if xr in rlist:
                return 0

    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def excepthook(exc_type, exc_value, exc_traceback):
    logger.critical("Unhandled exception:", exc_info=(exc_type, exc_value, exc_traceback))


def configure_logging():
    level = os.environ.get("CERTMONGER_EXPORTER_LOG_LEVEL", None)
    if level is None:
        level = "DEBUG" if os.isatty(sys.stdin.fileno()) else "INFO"

    if "INVOCATION_ID" in os.environ:
        handlers = [JournalHandler(SYSLOG_IDENTIFIER="certmonger-exporter")]
    else:
        handlers = None

    logging.basicConfig(
        level=level.upper(),
        handlers=handlers,
        format="%(message)s",
    )
    logging.captureWarnings(True)


# vim: ts=8 sts=4 sw=4 et
