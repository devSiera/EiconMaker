# EiconMaker

A lightweight desktop utility for generating F-List style eicons from GIFs and images.

Supports automatic slicing, overlays, borders, circular frames, compression, and preset saving.

---

# Features

* GIF support (`.gif`)
* Image support (`.png`, `.jpg`, `.jpeg`)
* Automatic eicon slicing:

  * 2x2
  * 3x3
  * 2x1
  * 1x2
  * 3x2
  * 2x3
  * etc.
* Square frame mode
* Circle frame mode
* Adjustable border thickness
* Custom border colors
* Overlay system with adjustable opacity
* Automatic GIF compression under 499 KB
* Drag & drop support
* Preset save/load system
* Dark themed UI
* Standalone executable support

---

# Circle Mode

Circle mode works like this:

1. The full canvas is resized first
2. A circular mask is applied
3. The circular border is drawn
4. The final image is sliced into eicons

This allows proper circular animated GIFs with transparent corners.

Circle mode only works with square grids like:

* 2x2
* 3x3

---

# Dependencies

Required Python packages:

```bash
pip install pillow tkinterdnd2 pyinstaller
```

Packages used:

* `Pillow` → image/GIF processing
* `tkinterdnd2` → drag & drop support
* `PyInstaller` → executable generation

---

# Running The Script

Run directly with Python:

```bat
py eiconmaker.py
```

Or:

```bat
python eiconmaker.py
```

---

# Included Files

## `eiconmaker.py`

Main source code.

Contains:

* UI
* GIF processing
* image slicing
* overlay system
* circle frame logic
* preset system
* compression pipeline

---

## `run.bat`

Simple launcher script.

Contents:

```bat
py eiconmaker.py
```

Double click it to launch the program quickly.

---

## `deploy.bat`

Build script for generating the standalone `.exe`.

Contents:

```bat
pyinstaller --noconfirm --onefile --windowed --icon=eiconmakerlogo.ico --add-data "eiconmakerlogo.ico;." --name "EiconMaker" eiconmaker.py
```

This:

* builds the executable
* applies the custom icon
* bundles the `.ico`
* generates the final executable inside `/dist`

---

# Notes

* Presets are stored locally as JSON
* Transparent GIF support is included
* Compression tries multiple optimization passes automatically
* The executable should be mostly plug-and-play

---

# Disclaimer

This is not an official F-List tool.

Shared as-is mainly as a small community utility project.
