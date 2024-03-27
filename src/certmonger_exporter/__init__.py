#!/usr/bin/python3

import logging
import os
import signal
import socket

from systemd.journal import JournalHandler

from . import waitpid_timeout
from .parent import main_parent
from .child import main_child


logger = logging.getLogger(__name__)


def main(argv):
    parent_sock, child_sock = socket.socketpair()
    pid = os.fork()
    if pid == 0:
        parent_sock.close()
        return main_child(child_sock)
    else:
        try:
            child_sock.close()
            return main_parent(pid, parent_sock)
        finally:
            # Tell child to exit
            parent_sock.shutdown(socket.SHUT_RDWR)

            try:
                pid_, status = waitpid_timeout.waitpid(pid, 0, 2)
            except waitpid_timeout.Timeout:
                logger.warning("Child did not exit itself, sending SIGKILL")
                os.kill(pid, signal.SIGKILL)
            else:
                if pid_ == 0:
                    logger.warning("Child process %r does not exist!?", pid)
                else:
                    logger.info("Child exit status: %r", status)


def excepthook(exc_type, exc_value, exc_traceback):
    logger.critical("Unhandled exception:", exc_info=(exc_type, exc_value, exc_traceback))


def configure_logging():
    level = os.environ.get("CERTMONGER_EXPORTER_LOG_LEVEL", "info").upper()
    if "INVOCATION_ID" in os.environ:
        handlers = [JournalHandler(SYSLOG_IDENTIFIER="certmonger-exporter")]
    else:
        handlers = None
    logging.basicConfig(
        level=level,
        handlers=handlers,
        format="%(message)s",
    )
    logging.captureWarnings(True)


# vim: ts=8 sts=4 sw=4 et
