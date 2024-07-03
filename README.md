# certmonger-exporter

A [Prometheus](https://prometheus.io/) exporter for [certmonger](https://pagure.io/certmonger).

Metrics are collected for each certificate tracking request, as well as for certmonger itself.

Based on the exported metrics, a set of [alerting rules](prometheus-rules.yaml)
are included.

## Exported metrics

```
# HELP certmonger_request_ca_error 1 if the CA returned an error when certificate signing was requested
# TYPE certmonger_request_ca_error gauge
certmonger_request_ca_error{ca="IPA",nickname="20240311111713",storage_location="/etc/pki/tls/certs/grafana.crt",storage_nickname="",storage_token="",storage_type="FILE"} 0.0

# HELP certmonger_request_key_generated_date_seconds Timestamp the private key was generated
# TYPE certmonger_request_key_generated_date_seconds gauge
certmonger_request_key_generated_date_seconds{ca="IPA",nickname="20240311111713",storage_location="/etc/pki/tls/certs/grafana.crt",storage_nickname="",storage_token="",storage_type="FILE"} 1.708974987e+09

# HELP certmonger_request_key_issued_count number of times a certificate was issued for the private key
# TYPE certmonger_request_key_issued_count gauge
certmonger_request_key_issued_count{ca="IPA",nickname="20240311111713",storage_location="/etc/pki/tls/certs/grafana.crt",storage_nickname="",storage_token="",storage_type="FILE"} 1.0

# HELP certmonger_request_last_checked_date_seconds Timestamp of last check for expiration
# TYPE certmonger_request_last_checked_date_seconds gauge
certmonger_request_last_checked_date_seconds{ca="IPA",nickname="20240311111713",storage_location="/etc/pki/tls/certs/grafana.crt",storage_nickname="",storage_token="",storage_type="FILE"} 1.711461319e+09

# HELP certmonger_request_not_valid_after_date_seconds Timestamp of certificate expiry
# TYPE certmonger_request_not_valid_after_date_seconds gauge
certmonger_request_not_valid_after_date_seconds{ca="IPA",nickname="20240311111713",storage_location="/etc/pki/tls/certs/grafana.crt",storage_nickname="",storage_token="",storage_type="FILE"} 1.720955834e+09

# HELP certmonger_request_not_valid_before_date_seconds Timestamp after which certificate is valid
# TYPE certmonger_request_not_valid_before_date_seconds gauge
certmonger_request_not_valid_before_date_seconds{ca="IPA",nickname="20240311111713",storage_location="/etc/pki/tls/certs/grafana.crt",storage_nickname="",storage_token="",storage_type="FILE"} 1.710155834e+09

# HELP certmonger_request_stuck 1 if request is stuck
# TYPE certmonger_request_stuck gauge
certmonger_request_stuck{ca="IPA",nickname="20240311111713",storage_location="/etc/pki/tls/certs/grafana.crt",storage_nickname="",storage_token="",storage_type="FILE"} 0.0

# HELP certmonger_requests_total Number of certificates managed by Certonger
# TYPE certmonger_requests_total gauge
certmonger_requests_total 1.0

# HELP certmonger_enabled 1 if the certmonger service is enabled
# TYPE certmonger_enabled gauge
certmonger_enabled 1.0
```

## How it works

The exporter queries certmonger via [its D-Bus
API](https://pagure.io/certmonger/blob/master/f/src/tdbus.h). Normally access
to this API is restricted to `root`; however we don't want to write a
network-facing service that runs as root.

The solution is to modify D-Bus policy to allow `nobody` to query certmonger,
and run the exporter as this non-privileged user.

**Note that this exposes sensitive properties of certificate tracking requests
to the `nobody` user**. This includes the `key-pin` property, which exposes the
password used to encrypt a request's private key file on disk. This is a
low-value secret which is itself stored on the disk in plain-text; access to
requests' private key files themselves is not granted.

If you prefer to use another user, you only need to edit [the D-Bus policy
file](certmonger-exporter.dbus.conf) and [the systemd unit
file](certmonger-exporter.service).

## How to install

To build an RPM you will need
[tito](https://github.com/rpm-software-management/tito?tab=readme-ov-file#install)
to be installed.

```
$ tito build --rpm --test
```

The last thing `tito` will do is print out the path of the RPM that it just
built. Pass this to `dnf install` to install the RPM.

To build an RPM in a clean chroot environment,
[mock](https://github.com/rpm-software-management/mock) can be used:

```
$ tito build --rpm --test --builder mock --arg mock=rhel-9-x86_64 --arg mock_args=--enable-network
```

To enable, start & test:

```
# systemctl enable --now certmonger-exporter.service

$ curl localhost:9632/metrics
```

To configure Prometheus to scrape the exporter:

```
# firewall-cmd --zone=public --permanent --add-port=9632/tcp && firewall-cmd --reload
```

and configure Prometheus like so:

```
scrape_configs:

- job_name: certmonger
  static_configs:
  - targets:
    - myhost.example.com:9632
```

Some configuration can be performed by setting environment variables (e.g., via
`Environment=` lines in `certmonger-exporter.service`):

* `CERTMONGER_EXPORTER_LOG_LEVEL`: set to `debug` for more logging; defaults to
  `info`
* `CERTMONGER_EXPORTER_PORT`: the exporter will listen on this port; defaults to `9632`

## Design

This exporter grew out of a cron job. It has been written with the following
goals in mind:

1. It should run on RHEL 8 (which ships Python 3.6)
2. It should not require dependencies outside of RHEL
3. It should consist of a single file
   (somewhat un-necessary now that we build an RPM)
4. The network-facing part of the exporter must not run as root
