import logging
import os
import pickle
import select
import signal
import socket

import dbus
from systemd.daemon import notify


DBUS_DBUS_PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"
CERTMONGER_DBUS_SERVICE = "org.fedorahosted.certmonger"
CERTMONGER_DBUS_CERTMONGER_OBJECT = "/org/fedorahosted/certmonger"
CERTMONGER_DBUS_CERTMONGER_INTERFACE = "org.fedorahosted.certmonger"
CERTMONGER_DBUS_REQUEST_INTERFACE = "org.fedorahosted.certmonger.request"
CERTMONGER_DBUS_CA_INTERFACE = "org.fedorahosted.certmonger.ca"


logger = logging.getLogger(__name__)


def main_parent(child_pid, parent_sock):
    xr, xw = os.pipe()
    def sigterm(signum, frame):
        notify("STOPPING=1")
        os.write(xw, b'\0')
    signal.signal(signal.SIGTERM, sigterm)

    bus = dbus.SystemBus()
    try:
        logger.debug("Waiting for child to be ready")
        data = parent_sock.recv(32)
        if data == b'':
            logger.error("Child failed to initialize")
            return 1
        elif data == b'ready':
            logger.debug("Child is ready")
            notify("READY=1")
            return service_requests_from_child(xr, parent_sock, bus)
        else:
            logger.error("Unexpected message from child: %r", data)
            return 1

    finally:
        bus.close()


def service_requests_from_child(xr, parent_sock, bus):
    while True:
        rlist, _, _ = select.select([xr, parent_sock], [], [])

        if xr in rlist:
            logger.debug("Bye")
            return 0

        if parent_sock in rlist:
            data = parent_sock.recv(32)
            if data == b'':
                logger.error("Child closed socket")
                return 1
            elif data == b'scrape-plz':
                logger.debug("Parent scraping...")
                data = pickle.dumps(list(parent_scrape(bus)), protocol=pickle.HIGHEST_PROTOCOL)
                parent_sock.sendall(data)
                logger.debug("Parent sent %s bytes to child", len(data))
            else:
                logger.error("Unknown message from child: %r", data)
                return 1


def parent_scrape(bus):
    certmonger = bus.get_object(CERTMONGER_DBUS_SERVICE, CERTMONGER_DBUS_CERTMONGER_OBJECT)

    for request_obj in certmonger.get_requests(dbus_interface=CERTMONGER_DBUS_CERTMONGER_INTERFACE):
        request = bus.get_object(CERTMONGER_DBUS_SERVICE, request_obj)
        request_props = dbus.Interface(request, DBUS_DBUS_PROPERTIES_INTERFACE)
        ca_obj = request_props.Get(CERTMONGER_DBUS_REQUEST_INTERFACE, "ca")
        if ca_obj.startswith("/org/fedorahosted/certmonger/requests/"):
            # Work around <https://issues.redhat.com/browse/RHEL-29246>
            ca_obj = ca_obj.replace("/org/fedorahosted/certmonger/requests/", "/org/fedorahosted/certmonger/cas/")
        ca = bus.get_object(CERTMONGER_DBUS_SERVICE, ca_obj)
        ca_props = dbus.Interface(ca, DBUS_DBUS_PROPERTIES_INTERFACE)
        labels = {
            "nickname": request_props.Get(CERTMONGER_DBUS_REQUEST_INTERFACE, "nickname"),
            "ca": ca_props.Get(CERTMONGER_DBUS_CA_INTERFACE, "nickname"),
            "storage_type":  request_props.Get(CERTMONGER_DBUS_REQUEST_INTERFACE, "cert-storage"),
        }
        if labels["storage_type"] == "FILE":
            labels["storage_location"] = request_props.Get(CERTMONGER_DBUS_REQUEST_INTERFACE, "cert-file")
            labels["storage_nickname"] = ""
            labels["storage_token"] = ""
        elif labels["storage_type"] == "NSSDB":
            labels["storage_location"] = request_props.Get(CERTMONGER_DBUS_REQUEST_INTERFACE, "cert-database")
            labels["storage_nickname"] = request_props.Get(CERTMONGER_DBUS_REQUEST_INTERFACE, "cert-nickname")
            labels["storage_token"] = request_props.Get(CERTMONGER_DBUS_REQUEST_INTERFACE, "cert-token")

        properties = {name: request_props.Get(CERTMONGER_DBUS_REQUEST_INTERFACE, name) for name in [
                        "ca-error", "key-issued-count", "ca-error",
                        "key-generated-date", "last-checked", "not-valid-after",
                        "not-valid-before", "stuck"
                    ]}

        yield labels, properties


# vim: ts=8 sts=4 sw=4 et
