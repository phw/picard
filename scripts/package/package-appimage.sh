#!/bin/bash

# This script builds an AppImage for MusicBrainz Picard.
# The main part of packaging the application with its dependencies
# is performed by PyInstaller. The resulting binaries are then put
# into the AppDir directory structure and packaged with appimagetool.
# See also https://docs.appimage.org/packaging-guide/manual.html

set -e

APP_ID="org.musicbrainz.Picard"
SOURCE_DIR=$(realpath "$(dirname $0)/../../")
BUILD_DIR="$SOURCE_DIR"/build
DIST_DIR="$SOURCE_DIR"/dist
APPIMAGE_DIR="$BUILD_DIR/$APP_ID.AppDir/"
ARCH=x86_64

APPIMAGETOOL_URL="https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-${ARCH}.AppImage"
FPCALC_URL="https://github.com/acoustid/chromaprint/releases/download/v1.5.1/chromaprint-fpcalc-1.5.1-linux-${ARCH}.tar.gz"

cd "$SOURCE_DIR"
PICARD_VERSION=$(python -c "import picard; print(picard.__version__)")

echo "Building AppImage for $APP_ID $PICARD_VERSION"

echo -e "\nBuild the binaries with PyInstaller..."
python setup.py build
pyinstaller picard.spec

echo -e "\nPrepare the appimage structure..."
rm -rf "$APPIMAGE_DIR" || true
mkdir -p "$APPIMAGE_DIR"
cd "$APPIMAGE_DIR"

echo -e "\nCopy picard binary install created by PyInstaller..."
mkdir opt
cp -rp "$SOURCE_DIR"/dist/picard/ opt/

echo -e "\nMake picard runnable from default path..."
mkdir -p usr/bin/
pushd usr/bin/
ln -s ../../opt/picard/picard-run picard
popd

echo -e "\nDownload latest pre-compiled AppRun..."
cp "$SOURCE_DIR/scripts/package/AppRun" .
chmod +x AppRun

echo -e "\nCopy desktop file and icons..."
mkdir -p usr/share/applications/
cp "$SOURCE_DIR/$APP_ID.desktop" usr/share/applications/
ln -s "usr/share/applications/$APP_ID.desktop" .
for size in 16x16 32x32 48x48 128x128 256x256; do
  mkdir -p "usr/share/icons/hicolor/$size/apps"
  cp -rp "$SOURCE_DIR/resources/images/$size/$APP_ID.png" \
    "usr/share/icons/hicolor/$size/apps/"
done
ln -s "usr/share/icons/hicolor/256x256/apps/$APP_ID.png" .

echo -e "\nCopy AppStream metadata..."
mkdir -p usr/share/metainfo/
cp "$SOURCE_DIR/$APP_ID.appdata.xml" usr/share/metainfo/

cd "$BUILD_DIR"

echo -e "\nDownload and unpack fpcalc..."
curl -LO "$FPCALC_URL"
tar xzf chromaprint-fpcalc-1.5.1-linux-x86_64.tar.gz
ls "$APPIMAGE_DIR"/usr/bin/
cp chromaprint-fpcalc-1.5.1-linux-x86_64/fpcalc "$APPIMAGE_DIR"/usr/bin/fpcalc

echo -e "\nPackage the AppImage..."
curl -Lo appimagetool "$APPIMAGETOOL_URL"
chmod +x appimagetool
./appimagetool "$APPIMAGE_DIR" "$DIST_DIR/MusicBrainz-Picard-${PICARD_VERSION}-${ARCH}.AppImage"
