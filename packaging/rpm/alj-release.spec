Name:           alj-release
Version:        @VERSION@
Release:        1%{?dist}
Summary:        Algorithm Local Judge DNF repository configuration
License:        MIT
BuildArch:      noarch
Source0:        algorithm-local-judge.repo

%description
Installs the signed Algorithm Local Judge DNF repository configuration.

%prep

%build

%install
mkdir -p %{buildroot}/etc/yum.repos.d
install -m 0644 %{SOURCE0} %{buildroot}/etc/yum.repos.d/algorithm-local-judge.repo

%files
%config(noreplace) /etc/yum.repos.d/algorithm-local-judge.repo

%changelog
* Thu Jan 01 1970 Algorithm Local Judge maintainers - @VERSION@-1
- Generated repository package.
