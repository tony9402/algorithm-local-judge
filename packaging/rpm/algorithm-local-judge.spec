Name:           algorithm-local-judge
Version:        @VERSION@
Release:        1%{?dist}
Summary:        Local web judge and problem authoring studio
License:        MIT
URL:            https://github.com/tony9402/algorithm-local-judge
Source0:        @SOURCE_ARCHIVE@
BuildArch:      x86_64
%global debug_package %{nil}
Requires:       ca-certificates
Recommends:     docker, gcc-c++, java-17-openjdk-headless, python3, pypy3

%description
Algorithm Local Judge contains the Judge and Problem Studio launchers. User data is
stored outside the RPM-owned /opt tree and is preserved during upgrade and erase.

%prep
%setup -q -n algorithm-local-judge

%build

%install
mkdir -p %{buildroot}/opt/algorithm-local-judge %{buildroot}/usr/bin
cp -a . %{buildroot}/opt/algorithm-local-judge/
ln -s /opt/algorithm-local-judge/bin/judge %{buildroot}/usr/bin/judge
ln -s /opt/algorithm-local-judge/bin/problem-studio %{buildroot}/usr/bin/problem-studio

%files
/opt/algorithm-local-judge
/usr/bin/judge
/usr/bin/problem-studio

%changelog
* Thu Jan 01 1970 Algorithm Local Judge maintainers - @VERSION@-1
- Generated release package.
