pkgname=omus
pkgver=1.0.4
pkgrel=1
pkgdesc='One Mouse Universal System for Linux'
arch=('any')
url='https://github.com/DonGeronimo7/OMUS'
license=('GPL-3.0-or-later')
depends=('python' 'python-evdev' 'python-dbus-next' 'python-packaging' 'systemd')
makedepends=('git' 'python-build' 'python-installer' 'python-setuptools')
# Stable source is pinned to the exact upstream release tag.
source=("omus::git+https://github.com/DonGeronimo7/OMUS.git#tag=v${pkgver}")
provides=('mouse-control')
conflicts=('mouse-control')
sha256sums=('SKIP')

build() {
  cd "$srcdir/omus"
  python -m build --wheel --no-isolation --outdir dist
}

package() {
  cd "$srcdir/omus"
  python -m installer --destdir="$pkgdir" dist/*.whl
  install -Dm644 src/mouse_control/udev/71-mouse-control-uaccess.rules \
    "$pkgdir/usr/lib/udev/rules.d/71-mouse-control-uaccess.rules"
  install -Dm644 packaging/appimage/omus.desktop "$pkgdir/usr/share/applications/omus.desktop"
  for size in 512 256 128 64 48 32 24 16; do
    install -Dm644 "assets/icons/hicolor/${size}x${size}/apps/omus.png" \
      "$pkgdir/usr/share/icons/hicolor/${size}x${size}/apps/omus.png"
  done
  install -Dm644 packaging/omus.metainfo.xml \
    "$pkgdir/usr/share/metainfo/io.github.DonGeronimo7.OMUS.metainfo.xml"
  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
  install -Dm644 CREDITS.md "$pkgdir/usr/share/doc/$pkgname/CREDITS.md"
  install -Dm644 SECURITY.md "$pkgdir/usr/share/doc/$pkgname/SECURITY.md"
}
