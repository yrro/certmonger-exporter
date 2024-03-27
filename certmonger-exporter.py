#!/usr/bin/python3

import logging
import os
import pickle
import pwd
import signal
import select
import socket
import threading
import sys

import dbus
from prometheus_client.core import GaugeMetricFamily, REGISTRY
from systemd.journal import JournalHandler
from systemd.daemon import notify


logger = logging.getLogger('certmonger-exporter')

DBUS_DBUS_PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"
CERTMONGER_DBUS_SERVICE = "org.fedorahosted.certmonger"
CERTMONGER_DBUS_CERTMONGER_OBJECT = "/org/fedorahosted/certmonger"
CERTMONGER_DBUS_CERTMONGER_INTERFACE = "org.fedorahosted.certmonger"
CERTMONGER_DBUS_REQUEST_INTERFACE = "org.fedorahosted.certmonger.request"
CERTMONGER_DBUS_CA_INTERFACE = "org.fedorahosted.certmonger.ca"
SYSTEMD_DBUS_SERVICE = "org.freedesktop.systemd1"
SYSTEMD_DBUS_MANAGER_OBJECT = "/org/freedesktop/systemd1"
SYSTEMD_DBUS_MANAGER_INTERFACE = "org.freedesktop.systemd1.Manager"
SYSTEMD_DBUS_UNIT_INTERFACE = "org.freedesktop.systemd1.Unit"

SOCKET_BUFFER_LEN = 512


class ChildDidNotRespond(Exception):
    pass


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

            def alarm(signum, frame):
                raise ChildDidNotRespond()
            signal.signal(signal.SIGALRM, alarm)

            signal.alarm(5)
            try:
                pid_, status = os.waitpid(pid, 0)
            except ChildDidNotRespond:
                logger.warning("Child did not exit itself, sending SIGKILL")
                os.kill(pid, signal.SIGKILL)
            else:
                signal.alarm(0)
                if pid_ == 0:
                    logger.warning("Child process %r does not exist!?", pid)
                else:
                    logger.info("Child exit status: %r", status)


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


def main_child(child_sock):
    # We don't want to recieve SIGINT from the developer's terminal.
    #os.setsid()

    pwent = pwd.getpwnam(os.environ.get("CERTMONGER_EXPORTER_USER", "nobody"))
    try:
        os.setgid(pwent.pw_gid)
        os.setuid(pwent.pw_uid)
    except PermissionError:
        logging.error("certmonger-exporter needs to be launched as root. The network-facing component will drop privileges by switching to the user %r.", pwent.pw_name)
        return 1

    main_sock, server_sock = socket.socketpair()

    REGISTRY.register(CertmongerCollector(server_sock))
    server, thread = start_httpd_server(int(os.environ.get("CERTMONGER_EXPORTER_PORT", "9630")))

    try:
        child_sock.sendall(b'ready')
        while True:
            logger.debug("Child waiting...")
            rlist, _, _ = select.select([child_sock, main_sock], [], [])

            if child_sock in rlist:
                data = child_sock.recv(32)
                if len(data) == 0:
                    logger.debug("Parent closed socket")
                    return 0
                else:
                    logger.error("Unexpected message from parent: %r", data)
                    return 1

            if main_sock in rlist:
                data = main_sock.recv(32)
                if len(data) == 0:
                    logger.error("Server closed socket!")
                    return 1
                elif data == b"scrape-plz":
                    main_sock.sendall(child_scrape(child_sock))
                else:
                    logger.error("Unexpected message from server: %r", data)
                    return 1

    finally:
        server.shutdown()
        thread.join()


def child_scrape(child_sock):
    logger.debug("Child requesting scrape from parent")
    child_sock.sendall(b"scrape-plz")
    data = b""
    while True:
        new_data = child_sock.recv(SOCKET_BUFFER_LEN)
        data += new_data
        if len(new_data) == SOCKET_BUFFER_LEN:
            continue
        elif len(new_data) == 0:
            raise Exception("Parent closed socket")
        else:
            break
    logger.debug("Child read %s bytes from parent", len(data))
    return data


# EPEL 8 has an older prometheus_client which don't return the thread for
# us to join on, so instead we re-implement it here.
def start_httpd_server(port, addr='', registry=REGISTRY):
    """Starts a WSGI server for prometheus metrics as a daemon thread."""
    from prometheus_client.exposition import make_wsgi_app, make_server, ThreadingWSGIServer, _SilentHandler, make_server
    app = make_wsgi_app(registry)
    httpd = make_server(addr, port, app, ThreadingWSGIServer, handler_class=_SilentHandler)
    t = threading.Thread(target=httpd.serve_forever)
    t.daemon = True
    t.start()
    return httpd, t


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


class CertmongerCollector:

    def __init__(self, sock):
        self.__sock = sock
        self.__bus = dbus.SystemBus()


    def __del__(self):
        self.__bus.close()


    def collect(self):
        logger.debug("Server collecting")
        self.__sock.sendall(b'scrape-plz')
        data = b''
        while True:
            new_data = self.__sock.recv(SOCKET_BUFFER_LEN)
            data += new_data
            if len(new_data) == SOCKET_BUFFER_LEN:
                continue
            elif len(new_data) == 0:
                # main thread has closed the socket, should never happen!
                return
            else:
                break

        requests = pickle.loads(data)
        logger.debug("Server unpickled %s requests from parent", len(requests))
        yield from self.collect_requests(requests)
        yield from self.collect_certmonger()


    def describe(self):
        '''
        If this method is present, the registry won't call collect during
        registration of the collector (which is problematic because it happens
        before we've sent the "ready" message to the parent.
        '''
        yield from self.collect_requests([])
        yield from self.collect_certmonger()


    def collect_certmonger(self):
        value = 0

        try:
            systemd_manager = self.__bus.get_object(SYSTEMD_DBUS_SERVICE, SYSTEMD_DBUS_MANAGER_OBJECT)

            unit_obj = systemd_manager.GetUnit("certmonger.service", dbus_interface=SYSTEMD_DBUS_MANAGER_INTERFACE)

            unit = self.__bus.get_object(SYSTEMD_DBUS_SERVICE, unit_obj)
            unit_file_state = unit.Get(SYSTEMD_DBUS_UNIT_INTERFACE, "UnitFileState", dbus_interface=DBUS_DBUS_PROPERTIES_INTERFACE)
            value = 1 if unit_file_state == "enabled" else 0
        except dbus.DBusException as e:
            logger.error("%s", e)

        yield GaugeMetricFamily("certmonger_enabled", "1 if the certmonger service is enabled; 0 if disabled or unknown", value=value)


    def collect_requests(self, requests):
        labelnames = ["nickname", "ca", "storage_type", "storage_location", "storage_nickname", "storage_token"]

        yield GaugeMetricFamily("certmonger_requests_total", "Number of certificates managed by Certonger", value=len(requests))

        mf_ca_error = GaugeMetricFamily("certmonger_request_ca_error", "1 if the CA returned an error when certificate signing was requested", labels=labelnames)
        mf_key_generated_date = GaugeMetricFamily("certmonger_request_key_generated_date_seconds", "Timestamp the private key was generated", labels=labelnames)
        mf_key_issued_count = GaugeMetricFamily("certmonger_request_key_issued_count", "number of times a certificate was issued for the private key", labels=labelnames)
        mf_last_checked = GaugeMetricFamily("certmonger_request_last_checked_date_seconds", "Timestamp of last check for expiration", labels=labelnames)
        mf_not_valid_after = GaugeMetricFamily("certmonger_request_not_valid_after_date_seconds", "Timestamp of certificate expiry", labels=labelnames)
        mf_not_valid_before = GaugeMetricFamily("certmonger_request_not_valid_before_date_seconds", "Timestamp after which certificate is valid", labels=labelnames)
        mf_stuck = GaugeMetricFamily("certmonger_request_stuck", "1 if request is stuck", labels=labelnames)

        for labels, properties in requests:
            labelvalues = [labels[labelname] for labelname in labelnames]

            mf_ca_error.add_metric(labelvalues, 1 if properties["ca-error"] else 0)
            if properties["key-generated-date"] > 0:
                # This date is not kept for some certificates. Don't know why.
                mf_key_generated_date.add_metric(labelvalues, properties["key-generated-date"])
            mf_key_issued_count.add_metric(labelvalues, properties["key-issued-count"])
            mf_last_checked.add_metric(labelvalues, properties["last-checked"])
            mf_not_valid_after.add_metric(labelvalues, properties["not-valid-after"])
            mf_not_valid_before.add_metric(labelvalues, properties["not-valid-before"])
            mf_stuck.add_metric(labelvalues, properties["stuck"])

        yield mf_ca_error
        yield mf_key_generated_date
        yield mf_key_issued_count
        yield mf_last_checked
        yield mf_not_valid_after
        yield mf_not_valid_before
        yield mf_stuck


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


def excepthook(exc_type, exc_value, exc_traceback):
    if exc_type is KeyboardInterrupt:
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("Unhandled exception!", exc_info=(exc_type, exc_value, exc_traceback))


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


if __name__ == '__main__':
    configure_logging()
    sys.excepthook = excepthook
    sys.exit(main(sys.argv))

# vim: ts=8 sts=4 sw=4 et
