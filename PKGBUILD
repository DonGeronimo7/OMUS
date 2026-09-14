pkgname=mouse-control
pkgver=0.7.4
pkgrel=1
pkgdesc='Headless evdev/uinput mouse remapping with optional hardware backends'
arch=('any')
url='https://github.com/DonGeronimo7/mouse-control'
license=('GPL-3.0-or-later')
depends=('python' 'python-evdev' 'python-dbus-next' 'systemd')
optdepends=('openrazer: optional Razer hardware integration')
source=("https://github.com/DonGeronimo7/mouse-control/releases/download/v${pkgver}/mouse_control-${pkgver}.tar.gz")
sha256sums=('a276ae3c5ef58df1707ed7fbca55e401cb46c35cd4406e86f7446779480b7dc6')

package() {
  cd "${pkgname}-${pkgver}"
  python -m installer --destdir="$pkgdir" dist/*.whl
  install -Dm644 src/mouse_control/udev/71-mouse-control-uaccess.rules \
    "$pkgdir/usr/lib/udev/rules.d/71-mouse-control-uaccess.rules"
  install -Dm644 packaging/appimage/mouse-control.desktop \
    "$pkgdir/usr/share/applications/mouse-control.desktop"
  for size in 512 256 128 64 48 32; do
    install -Dm644 "assets/icons/hicolor/${size}x${size}/apps/mouse-control.png" \
      "$pkgdir/usr/share/icons/hicolor/${size}x${size}/apps/mouse-control.png"
  done
  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
