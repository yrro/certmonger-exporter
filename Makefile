INSTALL ?= install
prefix ?= /usr/local
sysconfdir ?= /etc
libexecdir ?= $(prefix)/libexec

.PHONY: all
all: certmonger-exporter.pyz

certmonger-exporter.pyz: src/certmonger_exporter/*.py
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
run:
	PYTHONSAFEPATH=1 PYTHONPATH=src PYTHONDEVMODE=1 python3 -m certmonger_exporter
