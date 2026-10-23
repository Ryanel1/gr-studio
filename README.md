# GR Studio

A small native desktop photo finisher for Ricoh GR IV. Runs locally with Qt Widgets; no browser runtime, account, cloud upload, or background service.

## Launch on this EndeavourOS machine

The app is already configured. Run `./run.sh` in this folder. A separate Linux executable is in `dist/GR-Studio/GR-Studio`. Keep its `_internal` folder beside it.

## Archive workspace

Archive uses a monochrome palette matched to the local Chrome City / Monochrome Linux scheme: charcoal surfaces, silver actions, and neutral selection outlines. File, Edit, and View menus use native Qt controls. Light, Color, Effects, Detail, Curve, and Mixer sections expand independently, as do Frame Layout/Paper and Upright/Manual; export stays available below the scrolling inspector. The histogram shows **source luminance**, sampled at no more than 256 × 256 pixels. It does not include edits or the paper frame. Vertical guides are solid white and horizontal guides are dashed white, both outlined against the photograph. No runtime dependencies were added.

## Workflow

1. Connect the GR IV with a USB-C data cable. Close other applications using its camera connection.
2. Click **Import from USB**. The camera list labels SD and internal memory separately. Large thumbnails load automatically for visible photos and continue as you scroll. You can select photos while previews load; **Retry previews** retries missing images.
3. Check individual files, or use **Select JPEGs**. Choose an import folder and click **Import selected**. Closing during a transfer stops after the current file.
4. Select a photo in the filmstrip. Click **Auto adjust** above the sliders for conservative tone and color suggestions, then fine-tune them. It uses the original photo each time, updates Exposure, Contrast, Highlights, Shadows, Saturation, and Warmth, and preserves your other tuning, geometry, frame, and caption. The **Adjust** tab groups Light, Color, Effects, Detail, Curve, and Mixer controls. **Straighten** offers Off, Level, Vertical, Auto, Full, and Guided perspective modes. Scroll the inspector to reach lower controls on a small window. Hold **Compare** to see the original.
5. In **Frame**, choose Polaroid (original shape or square crop), Even border, or Fit canvas. Canvas ratios include 1:1, 4:5, 9:16, 3:2, 2:3, and 16:9 without cropping the photo. Adjust border width and rounded corners; Polaroid also has a bottom margin and caption. Expand **Paper** to choose backgrounds: a solid preset/custom color, the photo’s average color, or a blurred version of the photo.
6. Click **Export to folder…**. Exports are full-resolution, sRGB JPEGs at quality 95. Existing names receive a suffix instead of being overwritten. **Show export folder** opens the output folder.

Select multiple photos with Ctrl-click (Command-click on Mac), Shift-click for a range, or **Select all**. **Auto adjust N photos** analyzes each selected original independently. In Frame, choose your frame settings, then **Apply border to N selected**; each photo keeps its own caption and adjustments. **Export N photos…** writes them together to one folder, processing one photo at a time. You can stop after the current photo; failed files are reported while the others continue. Manual sliders, caption, geometry, and reset affect the previewed photo only. Existing geometry is preserved during batch Auto adjust and border application.

Edits persist automatically outside the originals, including each photo’s curve and all mixer bands. Older sessions open with neutral defaults for the added controls. Reset photo returns the previewed photo to the source. Removing from the session only removes the workspace entry. Camera operations in the shipped importer are read-only.

On KDE Linux, the export picker includes your saved network places (including **NAS**). Click **NAS**, open a share, and choose an export folder. GR Studio uses the installed KIO Fuse service and desktop authentication, remembers the network URL, and reconnects on the next export. If connection fails, open the NAS in Dolphin and sign in before retrying. On macOS, mount the NAS in Finder and choose its folder under `/Volumes`. No network credentials are stored by GR Studio.

Shortcuts: Ctrl+O opens local photos; Ctrl+I opens USB import; Ctrl+E exports.

## Tuning controls

The Adjust sections appear in this order; Light starts expanded:

- **Light:** Exposure, Contrast, Highlights, Shadows, Whites, and Blacks.
- **Color:** Warmth, Tint, Vibrance, and Saturation.
- **Effects:** Texture, Clarity, Dehaze, Grain, and Vignette. Negative Vignette darkens corners; positive values lighten them.
- **Detail:** Sharpening and Noise reduction.
- **Curve:** Linear, Soft contrast, Faded shadows, or Strong contrast. The read-only graph uses the same curve function as rendering.
- **Mixer:** Red, Orange, Yellow, Green, Aqua, Blue, Purple, and Magenta, each with Hue, Saturation, and Luminance. Switching bands preserves the other bands’ values; switching photos restores that photo’s settings.

These controls are lightweight photographic approximations for rendered images, not Adobe RAW processing or recovery of clipped detail. Preview and export share the tuning pipeline. Noise reduction operates on neighboring pixels and grain is generated per pixel, so their appearance differs between a downsampled preview and a full-resolution export. Inspect exported detail at 100% in an image viewer.

## Perspective correction

Open **Straighten**, choose **Vertical**, then **Apply** for automatic vertical correction. For **Guided**, drag two guides on separate edges that should be vertical. Use the direction selector to draw horizontal guides instead, or add a second pair. Click **Apply guides**. The original is shown while drawing so guides are independent of prior edits. **Undo guide** removes the last line; **Cancel** or Escape restores the previous view without changing edits. To redraw an existing correction, click **Draw guides**.

**Manual adjustments** reveals Vertical, Horizontal, Aspect, and Rotate. **Reset geometry** clears only perspective/rotation, preserving color edits and the frame. Corrections are saved and applied at full resolution before framing on export. Guided coordinates are converted into a saved transform; guide handles themselves are not restored for later editing.

## Current scope

- JPEG, PNG, and TIFF editing. DNG files can be copied from the camera, but RAW development is not included; edit the matching JPEG.
- Level corrects roll. Vertical automatically rectifies agreeing vertical edges. Auto uses reliable vertical/horizontal families with a vertical fallback for excessive cropping; Full requires both families. These are independent lightweight algorithms, not Adobe’s algorithms. Detection can abstain or select the wrong scene edges; inspect the result and use Guided when needed. Geometry uses a centered crop to remove empty edges.
- Polaroid Square uses a centered crop; Fit canvas adds space around the whole photo. Border width, bottom margin, and corner radius are percentages of the photo’s shorter side. Background color and blur are calculated independently for each photo during batch processing. Very large combinations above 160 megapixels are rejected before allocating the canvas. Freeform crop, textured paper, wireless transfer, and undo history are not part of this first version.
- Linux tested with the connected GR IV. SD listing, thumbnails, and original download are verified. Both storage IDs are exposed, but no internal-memory photos were available for transfer testing.
- The USB adapter currently accepts exactly one GR IV with USB ID 25fb:2123. Disconnect other MTP devices before importing.
- macOS source support is prepared but **not yet tested or packaged**. Linux binaries do not run on macOS.

## Lightweight behavior

Only Qt Essentials is required; Chromium, WebEngine, PDF and QML runtimes are excluded. The editor keeps a bounded preview, uses JPEG decoder downsampling, processes tone, mixer, and detail float calculations in strips, and uses a small NumPy/Pillow horizon detector instead of a video-processing toolkit. Full-resolution export temporarily needs more memory; spatial effects also use full-size byte images while float work stays bounded to strips. Thumbnails are cached locally. Uncached previews open a direct MTP session without enumerating the camera contents again; measured on the connected GR IV at 0.14–0.16 seconds each, versus about 2.25 seconds with the original reader.

On the development EndeavourOS machine, the native app with one 26MP JPEG open used about 155 MiB RSS at idle. Loading its 1400px preview took about 0.25 seconds in the UI smoke test. These are local measurements, not cross-platform guarantees.

## Source setup

Use Python 3.14 (the pinned dependency versions were verified with it).

EndeavourOS/Arch system dependency:

```sh
sudo pacman -S libmtp
./run.sh
```

macOS preparation on the Mac:

```sh
brew install python@3.14 libmtp
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m gr_studio
```

Create a fresh virtual environment on each OS; do not copy the Linux `.venv` to the Mac. macOS camera permissions/device behavior still need verification. Apple Photos or Image Capture may hold the camera; quit them if the importer reports that it cannot open the device.

## Development and verification

```sh
.venv/bin/python -m pip install pytest ruff pyinstaller
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
.venv/bin/ruff check gr_studio tests --select F
```

The Qt integration tests exercise editing, export, original preservation, session restoration and rapid photo switching. Image tests cover orientation, decoder previews, straightening, borders, color and safe export naming. Camera tests cover parsing, selection guards and failed-transfer cleanup. Hardware smoke tests were also run separately against the connected camera.

Session files use Qt's application-data location: normally `~/.local/share/GRStudio/GR Studio/` on Linux and `~/Library/Application Support/GRStudio/GR Studio/` on macOS. Deleting that app-specific folder resets session edits and cached thumbnails, not originals.

The source is split into `camera.py`, `imaging.py`, `state.py`, `workers.py`, `widgets.py`, `frames.py`, `frame_panel.py`, `tuning.py`, `tuning_panel.py`, `batch.py`, `import_dialog.py`, and `window.py` so platform adapters and the UI can evolve separately.

Frame controls are inspired by the photo features in [White Border’s official App Store listing](https://apps.apple.com/us/app/white-border/id1232787087), reviewed October 23, 2026. GR Studio retains its own desktop UI and Polaroid styles.
