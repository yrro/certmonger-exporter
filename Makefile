certmonger-exporter.pyz: src/certmonger_exporter/*.py
	python3 -m zipapp -o certmonger-exporter.pyz src

.PHONY: install
install: certmonger-exporter.pyz
	install -t /usr/local/libexec -m 755 certmonger-exporter.pyz
	install -t /etc/systemd/system certmonger-exporter.service

.PHONY: run
run:
	sudo PYTHONSAFEPATH=1 PYTHONPATH=src PYTHONDEVMODE=1 python3 -m certmonger_exporter
