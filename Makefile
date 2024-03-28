certmonger-exporter.pyz: src/certmonger_exporter/*.py
	python3 -m zipapp -o certmonger-exporter.pyz src

.PHONY: install
install: certmonger-exporter.pyz
	install -t /usr/local/libexec -m 755 certmonger-exporter.pyz
	install -t /etc/systemd/system certmonger-exporter.service
	install -t /etc/dbus-1/system.d certmonger-exporter.dbus.conf

.PHONY: run
run:
	PYTHONSAFEPATH=1 PYTHONPATH=src PYTHONDEVMODE=1 python3 -m certmonger_exporter
