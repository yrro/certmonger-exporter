Name:           certmonger-exporter
Version:        0.1
Release:        1%{?dist}
Summary:        Prometheus exporter for Certmonger

License:        GPLv3
URL:            https://github.com/yrro/certmonger-exporter
Source0:        %{name}-%{version}.tar.gz

BuildRequires:  make
BuildRequires:  python3-devel
BuildRequires:  python3-pip
BuildRequires:  systemd-rpm-macros
Requires:       python3
Requires:       python3-systemd
Requires:       python3-dbus
Requires:       certmonger

BuildArch:      noarch


%description
Collects metrics for monitoring certmonger's certificate tracking requests, as
well as certmonger itself.


%prep
%autosetup


%build
%make_build libexecdir=%{_libexecdir} datadir=%{_datadir} PYTHON=%{__python3}


%install
rm -rf "$RPM_BUILD_ROOT"
%make_install sysconfdir=%{_sysconfdir} prefix=%{_prefix} libexecdir=%{_libexecdir} datadir=%{_datadir} mandir=%{_mandir} PYTHON=%{__python3}
install -d %{?buildroot}%{_prefix}/lib
mv -t %{?buildroot}%{_prefix}/lib %{?buildroot}/etc/systemd/
install -d %{?buildroot}%{_datadir}
mv -t %{?buildroot}%{_datadir} %{?buildroot}/etc/dbus-1


%files
%{_datadir}/dbus-1/system.d/certmonger-exporter.dbus.conf
%{_prefix}/lib/systemd/system/certmonger-exporter.service
%{_libexecdir}/certmonger-exporter.pyz
%{_mandir}/man8/certmonger-exporter.8.gz
%{_defaultdocdir}/certmonger-exporter/prometheus-rules.yaml
%license COPYING


%post
%systemd_post certmonger-exporter.service


%preun
%systemd_preun certmonger-exporter.service


%postun
%systemd_postun_with_restart certmonger-exporter.service



%changelog
* Wed Apr 03 2024 Sam Morris <sam@robots.org.uk> 0.1-1
- new package built with tito

* Thu Mar 28 2024 Sam Morris <sam@robots.org.uk>
- Initial package
