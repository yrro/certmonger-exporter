import logging
import os
import pickle
import pwd
import select
import socket
import threading

import dbus
from prometheus_client.core import GaugeMetricFamily, REGISTRY


SOCKET_BUFFER_LEN = 4096


logger = logging.getLogger(__name__)


def main_child(child_sock):
    pwent = pwd.getpwnam(os.environ.get("CERTMONGER_EXPORTER_USER", "nobody"))
    try:
        os.setgid(pwent.pw_gid)
        os.setuid(pwent.pw_uid)
    except PermissionError:
        logging.error("certmonger-exporter needs to be launched as root. The network-facing component will drop privileges by switching to the user %r.", pwent.pw_name)
        return 1

    collector = CertmongerCollector()
    REGISTRY.register(collector)
    server, thread = start_httpd_server(int(os.environ.get("CERTMONGER_EXPORTER_PORT", "9630")))

    try:
        child_sock.sendall(b'ready')
        while True:
            logger.debug("Child waiting...")
            rlist, _, _ = select.select([child_sock, collector.scrape_request_pipe], [], [])

            if child_sock in rlist:
                data = child_sock.recv(4)
                if len(data) == 0:
                    logger.debug("Parent closed socket")
                    return 0
                else:
                    logger.error("Unexpected message from parent: %r", data)
                    return 1

            if collector.scrape_request_pipe in rlist:
                os.read(collector.scrape_request_pipe, 1)

                data = child_scrape(child_sock)
                requests = pickle.loads(data)
                logger.debug("Child unpickled %s requests from parent", len(requests))
                collector.consume(requests)

    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def child_scrape(child_sock):
    logger.debug("Child requesting scrape from parent...")
    child_sock.sendall(b"scrape-plz")
    data_len = int.from_bytes(sock_recv_len(child_sock, 4), byteorder='big')
    return sock_recv_len(child_sock, data_len)


def sock_recv_len(sock, nbytes):
    data = b""
    while len(data) < nbytes:
        new_data = sock.recv(nbytes-len(data))
        if len(new_data) == 0:
            raise Exception("Socket was closed by peer")
        data += new_data
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


class CertmongerCollector:
    DBUS_DBUS_PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"
    SYSTEMD_DBUS_SERVICE = "org.freedesktop.systemd1"
    SYSTEMD_DBUS_MANAGER_OBJECT = "/org/freedesktop/systemd1"
    SYSTEMD_DBUS_MANAGER_INTERFACE = "org.freedesktop.systemd1.Manager"
    SYSTEMD_DBUS_UNIT_INTERFACE = "org.freedesktop.systemd1.Unit"

    def __init__(self):
        self.__bus = dbus.SystemBus()
        self.__scraped_condition = threading.Condition()
        self.__requests = None
        self.scrape_request_pipe, self.__scrape_request_pipe_wr = os.pipe()


    def __del__(self):
        self.__bus.close()


    def consume(self, data):
        with self.__scraped_condition:
            self.__requests = data
            self.__scraped_condition.notify()


    def collect(self):
        logger.debug("Server collecting")
        os.write(self.__scrape_request_pipe_wr, b"\0")

        with self.__scraped_condition:
            self.__scraped_condition.wait_for(lambda: not self.__requests is None)
            yield from self.collect_requests(self.__requests)
            self.__requests = None

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
            systemd_manager = self.__bus.get_object(self.SYSTEMD_DBUS_SERVICE, self.SYSTEMD_DBUS_MANAGER_OBJECT)

            unit_obj = systemd_manager.GetUnit("certmonger.service", dbus_interface=self.SYSTEMD_DBUS_MANAGER_INTERFACE)

            unit = self.__bus.get_object(self.SYSTEMD_DBUS_SERVICE, unit_obj)
            unit_file_state = unit.Get(self.SYSTEMD_DBUS_UNIT_INTERFACE, "UnitFileState", dbus_interface=self.DBUS_DBUS_PROPERTIES_INTERFACE)
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


# vim: ts=8 sts=4 sw=4 et
