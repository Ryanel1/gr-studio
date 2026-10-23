# GR Studio
<!-- impeccable:product-schema 1 -->

## Platform
Native desktop: EndeavourOS Linux and macOS.

## Users and purpose
A Ricoh GR IV owner imports photos by USB-C, makes light edits, straightens horizons, adds an old-school Polaroid border, and exports JPEGs to a folder. Lightroom, White Border, and GR World are workflow references. The user explicitly wants a lightweight app and a dark photo workspace.

## Stack
Implementation choice: Python with Qt Widgets (PySide6 Essentials), Pillow, NumPy with a bounded horizon detector, and libmtp command-line tools for USB. No embedded browser or service. Mac USB requires validation with actual hardware; Linux libmtp detection, listing and one original download have been verified.

## Constraints
Original files preserved. Full-resolution export; bounded previews. Local processing. JPEG editing first; DNG import supported, RAW development is outside this first version. macOS source compatibility is intended, not yet verified. GR Studio is a working name chosen for this prototype.

## Evidence
A real GR IV exposed both SD and internal memory, listed 170 files from SD, and successfully downloaded a 6192x4128 JPEG. Internal memory had no files in that listing. The test photo is /home/deepx/Projects/GR Studio/outputs/usb-import-test/R0000001.JPG.
