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

## How to run

On CentOS Stream or RHEL, [enable
EPEL](https://docs.fedoraproject.org/en-US/epel/#_quickstart), then:

```
$ python3 -m zipapp -o certmonger-exporter.pyz src

# dnf install python3-systemd python3-dbus python3-prometheus_client

# install -t /usr/local/libexec -m 755 certmonger-exporter.pyz

# install -t /etc/systemd/system certmonger-exporter.service

# systemctl daemon-reload

# systemctl enable --now certmonger-exporter.service

# curl localhost:9630/metrics
```

Some configuration can be performed by setting environment variables (e.g., via
`Environment=` lines in `certmonger-exporter.service`):

* `CERTMONGER_EXPORTER_LOG_LEVEL`: set to `debug` for more logging; defaults to
  `info`
* `CERTMONGER_EXPORTER_PORT`: the exporter will listen on this port; defaults to `9630`
* `CERTMONGER_EXPORTER_USER`: the network-facing part of the exporter will
  run as this user; defaults to `nobody`

## Design

This exporter grew out of a cron job. It has been written with the following
goals in mind:

1. It should run on RHEL 8 (which ships Python 3.6)
2. It should not require any dependencies outside of RHEL or EPEL
3. It should consist of a single file
4. While only the root user may query certmonger, the network-facing part of
   the exporter should run as a non-privileged user
