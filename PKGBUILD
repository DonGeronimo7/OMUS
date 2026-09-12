pkgname=mouse-control
pkgver=0.6.9
pkgrel=1
pkgdesc='Headless evdev/uinput mouse remapping with optional hardware backends'
arch=('any')
url='https://github.com/DonGeronimo7/mouse-control'
license=('GPL-3.0-or-later')
depends=('python' 'python-evdev' 'python-dbus-next' 'systemd')
optdepends=('openrazer: optional Razer hardware integration')
source=("${pkgname}-${pkgver}.tar.gz")
sha256sums=('SKIP')

package() {
  cd "${pkgname}-${pkgver}"
  python -m installer --destdir="$pkgdir" dist/*.whl
  install -Dm644 src/mouse_control/udev/71-mouse-control-uaccess.rules \
    "$pkgdir/usr/lib/udev/rules.d/71-mouse-control-uaccess.rules"
  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
