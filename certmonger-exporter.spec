Name:           certmonger-exporter
Version:        main
Release:        1%{?dist}
Summary:        Prometheus exporter for Certmonger

License:        GPLv3
URL:            https://github.com/yrro/certmonger-exporter
Source0:        https://github.com/yrro/certmonger-exporter/archive/refs/heads/%{version}.tar.gz#/%{name}-%{version}.tar.gz

BuildRequires:  make
BuildRequires:  python3
Requires:       python3
Requires:       python3-systemd
Requires:       python3-dbus
Requires:       certmonger

BuildArch:      noarch


%description
Exports metrics allowing the monitoring of certmonger's certificate tracking
requests, as well as certmonger itself.

%global debug_package %{nil}

%prep
%autosetup


%build
%make_build


%install
rm -rf "$RPM_BUILD_ROOT"
%make_install sysconfdir:=%{_sysconfdir} prefix:=%{_prefix} libexecdir:=%{_libexecdir}


%files
%{_sysconfdir}/dbus-1/system.d/certmonger-exporter.dbus.conf
%{_sysconfdir}/systemd/system/certmonger-exporter.service
%{_libexecdir}/certmonger-exporter.pyz
%license COPYING
%doc README.md
%doc prometheus-rules.yaml


%post
%systemd_post certmonger-exporter.service


%preun
%systemd_preun certmonger-exporter.service


%postun
%systemd_postun_with_restart certmonger-exporter.service



%changelog
* Thu Mar 28 2024 Sam Morris <sam@robots.org.uk>
- Initial package
