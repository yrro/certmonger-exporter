import logging
import os

import dbus
from prometheus_client.core import GaugeMetricFamily


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


logger = logging.getLogger(__name__)


class CertmongerCollector:


    def __init__(self):
        self.__bus = dbus.SystemBus()


    def __del__(self):
        self.__bus.close()


    def collect(self, describe=False):
        yield from self.__collect_certmonger(describe)
        yield from self.__collect_requests(describe)


    def describe(self):
        yield from self.collect(describe=True)


    def __collect_certmonger(self, describe):
        mf_enabled = GaugeMetricFamily("certmonger_enabled", "1 if the certmonger service is enabled; 0 if disabled or unknown")

        if not describe:
            systemd_manager = self.__bus.get_object(SYSTEMD_DBUS_SERVICE, SYSTEMD_DBUS_MANAGER_OBJECT)

            try:
                unit_obj = systemd_manager.GetUnit("certmonger.service", dbus_interface=SYSTEMD_DBUS_MANAGER_INTERFACE)
            except dbus.DBusException as e:
                if e.get_dbus_name() == "org.freedesktop.systemd1.NoSuchUnit":
                    logger.warning(f"{e.get_dbus_name()} certmonger.service; is certmonger installed?")
                    value = 0
                else:
                    raise
            else:
                unit = self.__bus.get_object(SYSTEMD_DBUS_SERVICE, unit_obj)
                unit_file_state = unit.Get(SYSTEMD_DBUS_UNIT_INTERFACE, "UnitFileState", dbus_interface=DBUS_DBUS_PROPERTIES_INTERFACE)
                value = 1 if unit_file_state == "enabled" else 0

            mf_enabled.add_metric([], value)

        yield mf_enabled


    def __collect_requests(self, describe):
        mf_up = GaugeMetricFamily("certmonger_up", "1 if certmonger was contactable via D-Bus")

        mf_requests_total = GaugeMetricFamily("certmonger_requests_total", "Number of certificates managed by Certmonger")
        labelnames = "nickname", "ca", "storage_type", "storage_location", "storage_nickname", "storage_token"
        mfs = [
            GaugeMetricFamily("certmonger_request_status", "State of each tracking request (MONITORING is good; there are a lot of states, and most are transient, so only the current state is emitted", labels=(*labelnames, "status")),
            GaugeMetricFamily("certmonger_request_ca_error", "1 if the CA returned an error when certificate signing was requested", labels=labelnames),
            GaugeMetricFamily("certmonger_request_key_generated_date_seconds", "Timestamp the private key was generated", labels=labelnames),
            GaugeMetricFamily("certmonger_request_key_issued_count", "number of times a certificate was issued for the private key", labels=labelnames),
            GaugeMetricFamily("certmonger_request_last_checked_date_seconds", "Timestamp of last check for expiration", labels=labelnames),
            GaugeMetricFamily("certmonger_request_not_valid_after_date_seconds", "Timestamp of certificate expiry", labels=labelnames),
            GaugeMetricFamily("certmonger_request_not_valid_before_date_seconds", "Timestamp after which certificate is valid", labels=labelnames),
            GaugeMetricFamily("certmonger_request_stuck", "1 if request is stuck", labels=labelnames),
        ]

        if not describe:
            mfs_by_name = {mf.name: mf for mf in mfs}

            try:
                certmonger = self.__bus.get_object(CERTMONGER_DBUS_SERVICE, CERTMONGER_DBUS_CERTMONGER_OBJECT)
            except dbus.DBusException as e:
                logger.exception("While getting service:%r object:%r: %s", CERTMONGER_DBUS_SERVICE, CERTMONGER_DBUS_CERTMONGER_OBJECT, e)
                up = 0
            else:
                up = 1
                for i, request_obj in enumerate(certmonger.get_requests(dbus_interface=CERTMONGER_DBUS_CERTMONGER_INTERFACE)):
                    request = self.__bus.get_object(CERTMONGER_DBUS_SERVICE, request_obj)
                    self.__collect_request(mfs_by_name, request)

                mf_requests_total.add_metric((), i+1)

            mf_up.add_metric((), up)

        yield mf_up
        yield mf_requests_total
        yield from mfs


    def __collect_request(self, mfs_by_name, request):

        request_props = dbus.Interface(request, DBUS_DBUS_PROPERTIES_INTERFACE)

        nickname = request_props.Get(CERTMONGER_DBUS_REQUEST_INTERFACE, "nickname")

        ca_obj = request_props.Get(CERTMONGER_DBUS_REQUEST_INTERFACE, "ca")
        if ca_obj.startswith("/org/fedorahosted/certmonger/requests/"):
            # Work around <https://issues.redhat.com/browse/RHEL-29246>
            ca_obj = ca_obj.replace("/org/fedorahosted/certmonger/requests/", "/org/fedorahosted/certmonger/cas/")

        ca = self.__bus.get_object(CERTMONGER_DBUS_SERVICE, ca_obj)
        ca_props = dbus.Interface(ca, DBUS_DBUS_PROPERTIES_INTERFACE)

        ca = ca_props.Get(CERTMONGER_DBUS_CA_INTERFACE, "nickname")

        storage_type = request_props.Get(CERTMONGER_DBUS_REQUEST_INTERFACE, "cert-storage")
        if storage_type  == "FILE":
            storage_location = request_props.Get(CERTMONGER_DBUS_REQUEST_INTERFACE, "cert-file")
            storage_nickname = ""
            storage_token = ""
        elif storage_type == "NSSDB":
            storage_location = request_props.Get(CERTMONGER_DBUS_REQUEST_INTERFACE, "cert-database")
            storage_nickname = request_props.Get(CERTMONGER_DBUS_REQUEST_INTERFACE, "cert-nickname")
            storage_token = request_props.Get(CERTMONGER_DBUS_REQUEST_INTERFACE, "cert-token")

        labelvalues = nickname, ca, storage_type, storage_location, storage_nickname, storage_token

        mfs_by_name["certmonger_request_status"].add_metric((*labelvalues, request_props.Get(CERTMONGER_DBUS_REQUEST_INTERFACE, "status")), 1)
        mfs_by_name["certmonger_request_ca_error"].add_metric(labelvalues, 1 if request_props.Get(CERTMONGER_DBUS_REQUEST_INTERFACE, "ca-error") else 0)

        key_generated_date = request_props.Get(CERTMONGER_DBUS_REQUEST_INTERFACE, "key-generated-date")
        if key_generated_date > 0:
            # This date is not kept for some certificates. Don't know why.
            mfs_by_name["certmonger_request_key_generated_date_seconds"].add_metric(labelvalues, key_generated_date)

        mfs_by_name["certmonger_request_key_issued_count"].add_metric(labelvalues, request_props.Get(CERTMONGER_DBUS_REQUEST_INTERFACE, "key-issued-count"))
        mfs_by_name["certmonger_request_last_checked_date_seconds"].add_metric(labelvalues, request_props.Get(CERTMONGER_DBUS_REQUEST_INTERFACE, "last-checked"))
        mfs_by_name["certmonger_request_not_valid_after_date_seconds"].add_metric(labelvalues, request_props.Get(CERTMONGER_DBUS_REQUEST_INTERFACE, "not-valid-after"))
        mfs_by_name["certmonger_request_not_valid_before_date_seconds"].add_metric(labelvalues, request_props.Get(CERTMONGER_DBUS_REQUEST_INTERFACE, "not-valid-before"))
        mfs_by_name["certmonger_request_stuck"].add_metric(labelvalues, request_props.Get(CERTMONGER_DBUS_REQUEST_INTERFACE, "stuck"))


# vim: ts=8 sts=4 sw=4 et
