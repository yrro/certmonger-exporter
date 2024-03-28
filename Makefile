INSTALL ?= install
prefix ?= /usr/local
sysconfdir ?= /etc
libexecdir ?= $(prefix)/libexec

.PHONY: all
all: certmonger-exporter.pyz

stamp-pip-install: requirements.txt
	python3 -m pip install -r requirements.txt -t src
	touch stamp-pip-install

src/__main__.py:
	ln -sr -t src src/certmonger_exporter/__main__.py

certmonger-exporter.pyz: stamp-pip-install $(find src -type f) src/__main__.py
	find src -name '*.pyc' -delete
	find src -name '*.pyo' -delete
	find src -name '__pycache__' -delete
	python3 -m zipapp -o certmonger-exporter.pyz src

certmonger-exporter.service: certmonger-exporter.service.in
	sed -e s,@libexecdir@,$(libexecdir), $< > $@

.PHONY: install
install: certmonger-exporter.pyz certmonger-exporter.service
	$(INSTALL) -d $(DESTDIR)$(libexecdir)
	$(INSTALL) -t $(DESTDIR)$(libexecdir) -m 644 certmonger-exporter.pyz
	$(INSTALL) -d $(DESTDIR)$(sysconfdir)/systemd/system
	$(INSTALL) -t $(DESTDIR)$(sysconfdir)/systemd/system -m 644 certmonger-exporter.service
	$(INSTALL) -d $(DESTDIR)$(sysconfdir)/dbus-1/system.d
	$(INSTALL) -t $(DESTDIR)$(sysconfdir)/dbus-1/system.d -m 644 certmonger-exporter.dbus.conf

.PHONY: run
run: stamp-pip-install
	PYTHONSAFEPATH=1 \
	  PYTHONPATH=src \
	  PYTHONDEVMODE=1 \
	  CERTMONGER_EXPORTER_LOG_LEVEL=debug \
	    python3 -m certmonger_exporter
