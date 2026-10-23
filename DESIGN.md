---
name: GR Studio
description: Archive, a monochrome native photo workspace matched to Chrome City Linux.
colors:
  canvas: "#141416"
  panel: "#1e1e20"
  input: "#262628"
  divider: "#363638"
  control-border: "#414143"
  text: "#dadadc"
  secondary-text: "#aaaaac"
  primary-hover: "#eeeeef"
  selection: "#39393b"
  selection-highlight: "#727274"
  button: "#2a2a2c"
  button-hover: "#353537"
  hover-border: "#6e6e70"
  disabled: "#242426"
  disabled-text: "#777779"
  disabled-border: "#303032"
  primary-disabled-text: "#808082"
  section-hover: "#272729"
  alternate-row: "#232325"
  scrollbar: "#505052"
  histogram: "#88888a"
  white: "#ffffff"
  paper-warm: "#f4f0e7"
  paper-vintage: "#e9dfc8"
  paper-black: "#000000"
typography:
  brand:
    fontFamily: "sans-serif"
    fontSize: "22px"
    fontWeight: 600
  title:
    fontFamily: "sans-serif"
    fontSize: "21px"
    fontWeight: 500
  section:
    fontFamily: "sans-serif"
    fontSize: "13px"
    fontWeight: 600
  body:
    fontFamily: "sans-serif"
    fontSize: "13px"
rounded:
  field: "4px"
  button: "5px"
  checkbox: "2px"
spacing:
  compact: "4px"
  small: "8px"
  control: "10px"
  medium: "12px"
  group: "16px"
  section: "20px"
  inspector: "24px"
components:
  button-secondary:
    backgroundColor: "{colors.button}"
    textColor: "{colors.text}"
    rounded: "{rounded.button}"
    padding: "9px 14px"
  button-primary:
    backgroundColor: "{colors.text}"
    textColor: "{colors.panel}"
    rounded: "{rounded.button}"
    padding: "9px 14px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.panel}"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.secondary-text}"
    rounded: "{rounded.button}"
    padding: "9px 14px"
  field:
    backgroundColor: "{colors.input}"
    textColor: "{colors.text}"
    rounded: "{rounded.field}"
    padding: "8px"
  inspector-tab:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.secondary-text}"
    padding: "14px 16px"
  section-toggle:
    backgroundColor: "transparent"
    textColor: "{colors.text}"
    padding: "17px 0"
  filmstrip-item:
    rounded: "{rounded.field}"
    padding: "6px"
  filmstrip-item-selected:
    backgroundColor: "{colors.selection}"
    textColor: "{colors.text}"
---

# Design System: GR Studio

## Overview

**Creative North Star: "Archive"**

Archive is the user-approved production direction: a monochrome native photo workspace matched to Chrome City Linux. Dark gray panels, a darker canvas, silver text, and restrained native controls keep the photograph dominant. The implementation uses PySide6 Qt Widgets with Fusion styling and the system sans-serif family.

This record describes the implemented desktop interface, including its working menus and editing controls. Source authority is `gr_studio/theme.py`, `widgets.py`, `window.py`, `tuning_panel.py`, `tuning.py`, `frame_panel.py`, `geometry_panel.py`, and `import_dialog.py`. macOS has not been visually validated.

**Key Characteristics:**

- Large aspect-correct photo preview
- Monochrome action, selection, and focus treatments
- Collapsible native inspector sections
- Persistent export footer
- Horizontal session filmstrip
- Native USB import table with checkboxes

## Colors

The interface uses closely spaced neutral grays. Silver primary actions and focus outlines provide contrast against charcoal controls. The darkest surface belongs to the photograph. Frontmatter records the actual Qt stylesheet and paper presets.

### Primary

Silver (`text`) supplies primary button backgrounds, keyboard focus outlines, filmstrip selection outlines, and active tab underlines. Primary button text uses the panel tone. Hover brightens the silver; disabled actions use the selection tone with dedicated disabled text.

### Neutral

Canvas, panel, input, and alternate-row tones establish surface hierarchy. Dividers and control borders remain visible but restrained. Secondary text identifies supporting information and idle numeric values. Histogram fill and unchecked checkbox outlines use the histogram gray. White is used for guide strokes and highlighted text.

Paper warm, vintage, white, and black are image-frame presets; custom and photo-derived frame colors remain available.

**The Monochrome Interface Rule.** Keep interface actions, selection, focus, and geometry guides neutral; image content and paper treatments may carry color.

## Typography

Use Qt's `sans-serif` family resolved by the desktop environment. The application sets a 10pt base font; its stylesheet sets normal widgets to the body pixel size. Brand, title, and section-label roles are recorded in frontmatter. Collapsible section headers use body size with weight 500. Do not add a downloaded font dependency.

Adjustment values are right-aligned in 64px-wide native spinboxes. They appear as quiet text at rest and reveal a field surface on hover or focus. The painted empty preview uses 18pt for the prompt and 11pt for its supporting line; these are point sizes, distinct from stylesheet pixels.

## Layout

The window opens at 1280 × 850 logical pixels with a 940 × 680 minimum. A top toolbar holds the brand, File/Edit/View native popup menus, and local/USB import actions. The main horizontal splitter gives the canvas flexible width and the inspector 360–460px, initially 400px. Inspector content has 24px padding.

The image area contains a filename/compare row, the centered preview, a session action row, and a horizontal filmstrip. The preview preserves aspect ratio within 26px horizontal and 24px vertical clearance. The filmstrip is 148px high with 140 × 114px cells and 110 × 76px thumbnail bounds. Extended selection, Select all, and selection counts support batch actions.

Adjust, Frame, and Straighten are native tabs above collapsible sections. Only the active tab contributes its preferred height. The inspector scrolls at smaller desktop heights. The export footer remains outside the scroll area, and the wrapping status line spans the bottom of the window.

The USB dialog opens at 1040 × 760 with a 780 × 580 minimum, 28px horizontal and 24px vertical margins, and 20px group spacing. Its native checkbox table uses 144px rows and 160 × 120px thumbnail bounds. A destination row and import count/actions sit below the table.

**The Persistent Export Rule.** Keep the export action outside the inspector scroll area.

Qt layouts, the splitter, scroll areas, and minimum sizes govern resizing; there are no browser or mobile breakpoints.

## Elevation & Depth

The application is flat: neighboring surface tones, thin dividers, outlines, and enabled states establish hierarchy. No decorative shadows, gradients, translucency, or motion are implemented. Interaction feedback is immediate. Geometry guides have a dark halo solely for visibility over photographs.

## Shapes

The overall composition is rectangular. Buttons use modest rounded corners; fields and filmstrip items use the smaller field radius. Selected filmstrip items have a thin silver outline, while active tabs use a two-pixel silver underline. Slider tracks are 3px high with 10px circular handles. Unchecked USB checkbox indicators are 16px square with a visible gray outline and slight corner rounding. Scrollbars are 8px thick with rounded handles.

## Components

### Menus and buttons

File, Edit, and View are QMenus opened by toolbar QToolButtons, with actions connected to the existing workflow. View provides tab selection and filmstrip visibility. Open photos and Import from USB use secondary buttons. Compare, Reset, and session actions use quiet buttons. Primary silver buttons serve Auto adjust, Upright Apply, export, and USB import. Focus uses a silver outline; hover and disabled states remain monochrome.

### Adjust

A 64px-high source-photo luminance histogram sits above Auto adjust. It samples the loaded source and does not represent the edited result. Sections appear in order: Light, Color, Effects, Detail, Curve, Mixer. Only Light starts expanded. Each adjustment pairs a label and numeric spinbox with a slider beneath.

Light contains Exposure, Contrast, Highlights, Shadows, Whites, and Blacks. Color contains Warmth, Tint, Vibrance, and Saturation. Effects contains Texture, Clarity, Dehaze, Grain, and Vignette; negative Vignette darkens corners and positive values lighten them. Detail contains Sharpening and Noise reduction.

Curve offers Linear, Soft contrast, Faded shadows, and Strong contrast in a native selector above a 150px read-only monochrome graph. The graph evaluates the renderer’s curve function. Mixer uses a native selector for Red, Orange, Yellow, Green, Aqua, Blue, Purple, and Magenta, with Hue, Saturation, and Luminance controls. Switching bands preserves their independent values. Photo selection restores that photo’s tuning; older sessions use neutral defaults.

Auto adjust processes selected photos individually, updating only Exposure, Contrast, Highlights, Shadows, Saturation, and Warmth while preserving the added creative tuning. Manual controls edit only the previewed photo. The shared preview/export engine uses lightweight photographic approximations, with float calculations processed in strips and no added dependencies. Per-pixel grain and noise reduction differ with preview downsampling; inspect exported detail at 100%.

### Frame

Style selects No border, Polaroid original/square, Even border, or Fit canvas. Layout starts expanded and Paper starts collapsed; both are hidden for No border. Canvas ratio appears for Fit canvas. Bottom margin and caption appear for Polaroid. Paper offers solid color, color from photo, or blurred photo; presets/custom picker appear for solid backgrounds. The caption is capped at 160 characters. Apply border to selected appears for multiple selected photos and copies frame settings while preserving each caption.

### Straighten and guides

Upright starts expanded and offers Off, Level, Vertical, Auto, Full, and Guided. Manual adjustments starts collapsed and exposes Vertical, Horizontal, Aspect, and Rotate. Reset geometry is a quiet action. Guided mode shows the original image, direction selector, guide count, Undo guide, and Cancel. Vertical guides are solid white; horizontal guides are dashed white. Both have a dark halo, endpoint circles, and numbers. Operational guidance appears only while needed. Competing actions are disabled during drawing or analysis.

### Preview, filmstrip, and export

The preview fits the entire edited image including its frame. Hold to compare temporarily shows the original. The empty state explains how to begin. Filmstrip selection combines a filled surface with an outline. Export remains visible in its footer; labels reflect selection counts. Progress and Stop after current appear during sequential batch work, and Show export folder appears after export. Status text reports progress, errors, and completion.

### USB import

Use the native checkable table with Photo, Storage, Format, and Size columns. Checkbox state determines import selection; ordinary row selection is disabled. Keep unchecked boxes visible on the dark surface. Thumbnail loading and camera scan states use the existing controls and status feedback. The destination row shows the folder name with its full path in a tooltip.

## Do's and Don'ts

- **Do** preserve the large, aspect-correct preview and persistent export action.
- **Do** use existing native controls, visible focus, and disabled states.
- **Do** keep section defaults and conditional control visibility aligned with the implementation.
- **Do** keep paper colors within the frame treatment.
- **Do** describe the histogram as source luminance.
- **Don't** add unsupported mock controls, dependencies, or web/mobile breakpoints.
- **Don't** introduce colored interface accents, heavy shadows, or decorative animation.
- **Don't** add static helper subtext where tooltips or operational status already provide guidance.
- **Don't** claim macOS visual validation without inspecting it there.
