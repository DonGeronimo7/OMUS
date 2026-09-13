pkgname=mouse-control
pkgver=0.7.2
pkgrel=1
pkgdesc='Headless evdev/uinput mouse remapping with optional hardware backends'
arch=('any')
url='https://github.com/DonGeronimo7/mouse-control'
license=('GPL-3.0-or-later')
depends=('python' 'python-evdev' 'python-dbus-next' 'systemd')
optdepends=('openrazer: optional Razer hardware integration')
source=("https://github.com/DonGeronimo7/mouse-control/releases/download/v${pkgver}/mouse_control-${pkgver}.tar.gz")
sha256sums=('d8f584bc4939f827e657e74bd1cf66867a2f7dbf077195fb48bcba8d9dd13f0d')

package() {
  cd "${pkgname}-${pkgver}"
  python -m installer --destdir="$pkgdir" dist/*.whl
  install -Dm644 src/mouse_control/udev/71-mouse-control-uaccess.rules \
    "$pkgdir/usr/lib/udev/rules.d/71-mouse-control-uaccess.rules"
  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
