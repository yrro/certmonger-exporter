INSTALL ?= install
PYTHON ?= python3
prefix ?= /usr/local
sysconfdir ?= /etc
libexecdir ?= $(prefix)/libexec
datadir ?= $(prefix)/share
mandir ?= $(datadir)/man
docdir ?= $(datadir)/doc
user ?= nobody
version = 0.1

.PHONY: all
all: certmonger-exporter.pyz certmonger-exporter.pyz certmonger-exporter.service certmonger-exporter.8 certmonger-exporter.dbus.conf

stamp-pip-install: requirements.txt
	PIP_REQUIRE_VIRTUALENV=false $(PYTHON) -m pip install -r requirements.txt -t src
	touch stamp-pip-install

src/__main__.py:
	ln -srf -t src src/certmonger_exporter/__main__.py

certmonger-exporter.pyz: stamp-pip-install $(find src -type f) src/__main__.py
	find src -name '*.pyc' -delete
	find src -name '*.pyo' -delete
	find src -name '__pycache__' -delete
	$(PYTHON) -m zipapp -o certmonger-exporter.pyz src

certmonger-exporter.service: certmonger-exporter.service.in
	< $< \
	  $(PYTHON) template.py \
	    python=$$(which $(PYTHON)) \
	    libexecdir=$(libexecdir) \
	    user=$(user) \
	    > $@

certmonger-exporter.8: certmonger-exporter.8.in
	< $< \
	  $(PYTHON) template.py \
	    prometheus_rules!groff_path=$(docdir)/prometheus-rules.yaml \
	    user!groff=$(user) \
	    version!groff=$(version) \
	    > $@

certmonger-exporter.dbus.conf: certmonger-exporter.dbus.conf.in
	< $< \
	  $(PYTHON) template.py \
	    user=$(user) \
	    > $@

.PHONY: install
install:
	$(INSTALL) -d $(DESTDIR)$(libexecdir)
	$(INSTALL) -t $(DESTDIR)$(libexecdir) -m 644 certmonger-exporter.pyz
	$(INSTALL) -d $(DESTDIR)$(sysconfdir)/systemd/system
	$(INSTALL) -t $(DESTDIR)$(sysconfdir)/systemd/system -m 644 certmonger-exporter.service
	$(INSTALL) -d $(DESTDIR)$(sysconfdir)/dbus-1/system.d
	$(INSTALL) -t $(DESTDIR)$(sysconfdir)/dbus-1/system.d -m 644 certmonger-exporter.dbus.conf
	$(INSTALL) -d $(DESTDIR)$(mandir)/man8
	$(INSTALL) -t $(DESTDIR)$(mandir)/man8 -m 644 certmonger-exporter.8
	gzip -9 $(DESTDIR)$(mandir)/man8/certmonger-exporter.8
	$(INSTALL) -d $(DESTDIR)$(docdir)/certmonger-exporter
	$(INSTALL) -t $(DESTDIR)$(docdir)/certmonger-exporter -m 644 prometheus-rules.yaml

.PHONY: run
run: stamp-pip-install
	PYTHONSAFEPATH=1 \
	  PYTHONPATH=src \
	  PYTHONDEVMODE=1 \
	  CERTMONGER_EXPORTER_LOG_LEVEL=debug \
	    $(PYTHON) -m certmonger_exporter
