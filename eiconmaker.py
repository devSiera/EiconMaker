from pathlib import Path
from PIL import Image, ImageSequence, ImageDraw
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
import threading
import shutil
import math
import re
import json
import sys

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False


MAX_SIZE_KB = 499
MAX_SIZE_BYTES = MAX_SIZE_KB * 1024
TILE_SIZE = 100
DEFAULT_BORDER_WIDTH = 5
MIN_BORDER_WIDTH = 1
MAX_BORDER_WIDTH = 20
ASPECT_RATIO_TOLERANCE = 0.03
PRESETS_FILENAME = "eicon_presets.json"
APP_ICON_FILENAME = "eiconmakerlogo.ico"

PRESET_COLORS = {
    "none": None,
    "red": "#ff0000",
    "orange": "#ff8000",
    "yellow": "#ffe600",
    "green": "#00c850",
    "cyan": "#00dcff",
    "purple": "#a03cff",
    "blue": "#286eff",
    "pink": "#ff5abe",
    "gray": "#8c8c8c",
    "brown": "#824b23",
    "white": "#ffffff",
    "black": "#000000",
    "custom": "custom",
}


HELP_TEXTS = {
    "input": "Select or drag the file you want to turn into an eicon grid. GIF mode accepts .gif. Image mode accepts .jpg, .jpeg, and .png.",
    "grid": (
        "Choose the grid layout.\n\n"
        "2x2 creates 4 output files.\n"
        "3x3 creates 9 output files.\n\n"
        "The input file aspect ratio must match the selected grid."
    ),
    "frame": (
        "Choose the output frame shape.\n\n"
        "Square keeps the normal 100x100 eicon tiles.\n"
        "Circle masks the full grid canvas first, draws the circular border, and then slices it.\n"
        "Circle mode only works with square grids like 2x2 or 3x3.\n\n"
        "If a border color is selected, circle mode draws the border around the full circular frame. "
        "Square mode draws the border around the full sliced grid before export."
    ),
    "border": (
        "Optional outer border.\n\n"
        "If set to none, no border is added.\n"
        "If a color is selected, a border is added around the full image before slicing.\n"
        "You can choose the border thickness in pixels. Default: 5px.\n\n"
        "The HEX field is optional. It is only editable and only used when you choose custom."
    ),
    "overlay": (
        "Optional color overlay.\n\n"
        "This adds a transparent color layer over the whole file before slicing.\n\n"
        "The HEX field is optional. It is only editable and only used when you choose custom."
    ),
    "opacity": "Controls overlay strength. 0% means invisible, 100% means full color. You can move the slider or type a number manually.",
    "presets": (
        "Save and reload named configuration presets.\n\n"
        "Presets store mode, grid, frame shape, border color, border HEX, border thickness, overlay color, overlay HEX, and opacity.\n\n"
        "They are saved as eicon_presets.json next to the .exe. If you run the .py directly, the file is saved next to the script."
    ),
    "ezgif": (
        "How to crop a GIF/image with EZGIF:\n\n"
        "1. Go to https://ezgif.com/crop\n"
        "2. Upload your GIF or image.\n"
        "3. In the crop tool, choose the aspect ratio that matches your grid:\n\n"
        "   2x2 or 3x3 = 1:1\n"
        "   2x1 = 2:1\n"
        "   1x2 = 1:2\n"
        "   3x1 = 3:1\n"
        "   1x3 = 1:3\n"
        "   3x2 = 3:2\n"
        "   2x3 = 2:3\n\n"
        "4. Move/resize the crop box until the important part is inside.\n"
        "5. Click Crop Image.\n"
        "6. Save/download the cropped GIF.\n"
        "7. Use that cropped GIF or image in this tool."
    ),
}


def get_grid_options():
    return ["2x2", "2x1", "1x2", "3x1", "1x3", "3x2", "2x3", "3x3"]


def get_frame_options():
    return ["Square", "Circle"]



def get_app_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent


def resource_path(relative_path: str) -> str:
    """
    Return the correct path for bundled resources.

    - Running as .py: uses the script folder.
    - Running as PyInstaller onefile .exe: uses sys._MEIPASS.

    This is needed for files bundled with --add-data, like eiconmakerlogo.ico.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return str(Path(sys._MEIPASS) / relative_path)

    return str(Path(__file__).resolve().parent / relative_path)


def get_presets_path() -> Path:
    return get_app_directory() / PRESETS_FILENAME


def load_presets_file() -> dict:
    presets_path = get_presets_path()

    if not presets_path.exists():
        return {}

    try:
        with presets_path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            return {}

        return data
    except Exception:
        return {}


def save_presets_file(presets: dict):
    presets_path = get_presets_path()

    with presets_path.open("w", encoding="utf-8") as file:
        json.dump(presets, file, indent=4, ensure_ascii=False)


def hex_to_rgb(value: str):
    value = value.strip()

    if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise RuntimeError(f"Invalid HEX color: {value}. Use format #RRGGBB.")

    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


def resolve_color(selection: str, custom_hex: str):
    if selection == "none":
        return None

    if selection == "custom":
        return hex_to_rgb(custom_hex)

    return hex_to_rgb(PRESET_COLORS[selection])


def normalize_border_width(value) -> int:
    try:
        border_width = int(float(str(value).strip()))
    except (TypeError, ValueError):
        border_width = DEFAULT_BORDER_WIDTH

    return max(MIN_BORDER_WIDTH, min(MAX_BORDER_WIDTH, border_width))


def simplify_ratio(width: int, height: int):
    divisor = math.gcd(width, height)
    return width // divisor, height // divisor


def validate_aspect_ratio(input_path: Path, cols: int, rows: int):
    with Image.open(input_path) as img:
        width, height = img.size

    input_ratio = width / height
    target_ratio = cols / rows

    if abs(input_ratio - target_ratio) > ASPECT_RATIO_TOLERANCE:
        input_simple = simplify_ratio(width, height)
        target_simple = simplify_ratio(cols, rows)

        raise RuntimeError(
            "Incorrect aspect ratio.\n\n"
            f"Selected grid: {cols}x{rows}\n"
            f"Required ratio: {target_simple[0]}:{target_simple[1]}\n\n"
            f"Your file size: {width}x{height}\n"
            f"Your file ratio: {input_simple[0]}:{input_simple[1]}\n\n"
            "Choose a matching grid or crop/resize the file first.\n\n"
            "Tip: use https://ezgif.com/crop to crop the GIF to the correct ratio."
        )


def validate_frame_shape(frame_shape: str, cols: int, rows: int):
    if frame_shape == "Circle" and cols != rows:
        raise RuntimeError(
            "Circle frame only works with square grids.\n\n"
            "Use 2x2 or 3x3, or switch Frame back to Square."
        )


def resize_exact(frame: Image.Image, width: int, height: int) -> Image.Image:
    return frame.convert("RGBA").resize((width, height), Image.Resampling.LANCZOS)


def apply_overlay(frame: Image.Image, color, opacity: int):
    if color is None or opacity <= 0:
        return frame

    frame = frame.convert("RGBA")
    alpha = int(255 * (opacity / 100))
    overlay = Image.new("RGBA", frame.size, (*color, alpha))

    return Image.alpha_composite(frame, overlay)


def add_border_to_canvas(frame: Image.Image, color, border_width: int = DEFAULT_BORDER_WIDTH) -> Image.Image:
    if color is None:
        return frame

    border_width = normalize_border_width(border_width)
    frame = frame.copy()
    draw = ImageDraw.Draw(frame)

    for i in range(border_width):
        draw.rectangle(
            [i, i, frame.width - 1 - i, frame.height - 1 - i],
            outline=color
        )

    return frame


def apply_circle_frame_to_canvas(frame: Image.Image, border_color, border_width: int = DEFAULT_BORDER_WIDTH) -> Image.Image:
    """
    Circle mode order:
    1. Resize/process full canvas.
    2. Apply circular transparent mask to the full canvas.
    3. Draw circular border.
    4. Slice the final canvas.
    """
    frame = frame.convert("RGBA")

    if frame.width != frame.height:
        raise RuntimeError("Circle frame only works with square grids such as 2x2 or 3x3.")

    size = frame.width
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse([0, 0, size - 1, size - 1], fill=255)

    output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    output.paste(frame, (0, 0), mask)

    if border_color is not None:
        border_width = normalize_border_width(border_width)
        draw = ImageDraw.Draw(output)

        for i in range(border_width):
            draw.ellipse(
                [i, i, size - 1 - i, size - 1 - i],
                outline=border_color
            )

    return output


def apply_frame_shape_to_canvas(frame: Image.Image, frame_shape: str, border_color, border_width: int) -> Image.Image:
    frame_shape = frame_shape or "Square"

    if frame_shape == "Square":
        return add_border_to_canvas(frame, border_color, border_width)

    if frame_shape == "Circle":
        return apply_circle_frame_to_canvas(frame, border_color, border_width)

    raise RuntimeError("Invalid frame shape selected. Choose Square or Circle.")


def load_processed_frames(gif_path: Path, cols: int, rows: int, frame_shape: str, border_color, overlay_color, overlay_opacity, border_width):
    img = Image.open(gif_path)

    canvas_w = cols * TILE_SIZE
    canvas_h = rows * TILE_SIZE

    frames = []
    durations = []

    for frame in ImageSequence.Iterator(img):
        duration = frame.info.get("duration", img.info.get("duration", 40))

        processed = resize_exact(frame, canvas_w, canvas_h)
        processed = apply_overlay(processed, overlay_color, overlay_opacity)
        processed = apply_frame_shape_to_canvas(processed, frame_shape, border_color, border_width)

        if processed is None:
            raise RuntimeError("Internal processing error: processed frame is None.")

        frames.append(processed)
        durations.append(duration)

    return frames, durations


def build_global_palette(frames, colors: int, frame_step: int):
    sampled = frames[::frame_step]

    if len(sampled) > 80:
        interval = max(1, len(sampled) // 80)
        sampled = sampled[::interval]

    sample_w = sampled[0].width
    sample_h = sampled[0].height * len(sampled)

    sheet = Image.new("RGB", (sample_w, sample_h))

    y = 0
    for frame in sampled:
        sheet.paste(frame.convert("RGB"), (0, y))
        y += frame.height

    return sheet.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)


def slice_frames(frames, durations, cols: int, rows: int, frame_step: int):
    total = cols * rows
    sliced = [[] for _ in range(total)]
    sliced_durations = []

    boxes = []

    for row in range(rows):
        for col in range(cols):
            x1 = col * TILE_SIZE
            y1 = row * TILE_SIZE
            boxes.append((x1, y1, x1 + TILE_SIZE, y1 + TILE_SIZE))

    for i in range(0, len(frames), frame_step):
        frame = frames[i]

        if frame is None:
            raise RuntimeError("Internal slicing error: frame is None.")

        sliced_durations.append(sum(durations[i:i + frame_step]))

        for index, box in enumerate(boxes):
            sliced[index].append(frame.crop(box))

    return sliced, sliced_durations


def save_gif(frames, durations, output_path: Path, palette):
    has_transparency = any(frame.convert("RGBA").getchannel("A").getextrema()[0] < 255 for frame in frames)

    paletted_frames = []

    if has_transparency:
        transparent_rgb = (255, 0, 255)

        for frame in frames:
            rgba = frame.convert("RGBA")
            background = Image.new("RGBA", rgba.size, (*transparent_rgb, 255))
            alpha = rgba.getchannel("A")
            composited = Image.alpha_composite(background, rgba).convert("RGB")
            paletted = composited.quantize(palette=palette)

            # Force transparent pixels to palette index 0.
            paletted.putpalette([255, 0, 255] + paletted.getpalette()[3:])
            mask = alpha.point(lambda a: 255 if a < 128 else 0)
            paletted.paste(0, mask=mask)
            paletted_frames.append(paletted)

        paletted_frames[0].save(
            output_path,
            save_all=True,
            append_images=paletted_frames[1:],
            duration=durations,
            loop=0,
            optimize=True,
            disposal=2,
            transparency=0,
        )
        return

    paletted_frames = [
        frame.convert("RGB").quantize(palette=palette)
        for frame in frames
    ]

    paletted_frames[0].save(
        output_path,
        save_all=True,
        append_images=paletted_frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )


def try_export(frames, durations, output_dir: Path, cols: int, rows: int, colors: int, frame_step: int):
    temp_dir = output_dir / "_eicon_temp"

    if temp_dir.exists():
        shutil.rmtree(temp_dir)

    temp_dir.mkdir(parents=True, exist_ok=True)

    sliced_frames, sliced_durations = slice_frames(frames, durations, cols, rows, frame_step)

    palette_source = []
    for part in sliced_frames:
        palette_source.extend(part)

    palette = build_global_palette(palette_source, colors, 1)
    output_names = [f"{i}.gif" for i in range(1, cols * rows + 1)]

    for name, part_frames in zip(output_names, sliced_frames):
        save_gif(part_frames, sliced_durations, temp_dir / name, palette)

    sizes = [(temp_dir / name).stat().st_size for name in output_names]

    if all(size <= MAX_SIZE_BYTES for size in sizes):
        for name in output_names:
            final_path = output_dir / name

            if final_path.exists():
                final_path.unlink()

            shutil.move(str(temp_dir / name), str(final_path))

        shutil.rmtree(temp_dir)
        return True, sizes

    shutil.rmtree(temp_dir)
    return False, sizes


def process_gif(
    gif_path: Path,
    grid: str,
    frame_shape: str,
    border_selection: str,
    border_custom_hex: str,
    border_width: int,
    overlay_selection: str,
    overlay_custom_hex: str,
    overlay_opacity: int,
    log
):
    if not gif_path.exists():
        raise RuntimeError("GIF file does not exist.")

    if gif_path.suffix.lower() != ".gif":
        raise RuntimeError("Please select a .gif file.")

    cols, rows = map(int, grid.lower().split("x"))

    validate_aspect_ratio(gif_path, cols, rows)
    validate_frame_shape(frame_shape, cols, rows)

    border_color = resolve_color(border_selection, border_custom_hex)
    overlay_color = resolve_color(overlay_selection, overlay_custom_hex)

    output_dir = gif_path.parent / f"eicon_output_{cols}x{rows}"
    output_dir.mkdir(exist_ok=True)

    log(f"Input: {gif_path.name}")
    log("Mode: GIF")
    log(f"Grid: {cols}x{rows}")
    log(f"Frame: {frame_shape}")
    log(f"Border: {border_selection}")
    log(f"Border thickness: {border_width}px")
    log(f"Overlay: {overlay_selection} at {overlay_opacity}%")
    log(f"Output folder: {output_dir}")
    log("")
    log("Aspect ratio validated.")
    log("Loading GIF frames...")

    frames, durations = load_processed_frames(
        gif_path,
        cols,
        rows,
        frame_shape,
        border_color,
        overlay_color,
        overlay_opacity,
        border_width
    )

    log(f"Frames loaded: {len(frames)}")
    log("Starting compression loop...")
    log("")

    attempts = []

    for frame_step in [1, 2, 3, 4, 5, 6, 8, 10]:
        for colors in [256, 224, 192, 160, 128, 96, 80, 64, 48, 32, 24, 16]:
            attempts.append((colors, frame_step))

    best_failed = None

    for colors, frame_step in attempts:
        log(f"Trying: {colors} colors | frame_step={frame_step}")

        success, sizes = try_export(
            frames,
            durations,
            output_dir,
            cols,
            rows,
            colors,
            frame_step
        )

        sizes_kb = [round(s / 1024, 2) for s in sizes]
        log(f"Sizes: {sizes_kb} KB")

        if success:
            log("")
            log("DONE.")
            log(f"Final shared settings: {colors} colors | frame_step={frame_step}")
            log("")

            for i, size in enumerate(sizes, start=1):
                log(f"{i}.gif: {round(size / 1024, 2)} KB")

            return output_dir

        best_failed = (colors, frame_step, sizes_kb)

    raise RuntimeError(
        "Could not compress every GIF under 499 KB. "
        f"Best last attempt: {best_failed}"
    )


def load_processed_image(image_path: Path, cols: int, rows: int, frame_shape: str, border_color, overlay_color, overlay_opacity, border_width):
    canvas_w = cols * TILE_SIZE
    canvas_h = rows * TILE_SIZE

    with Image.open(image_path) as img:
        processed = resize_exact(img, canvas_w, canvas_h)

    processed = apply_overlay(processed, overlay_color, overlay_opacity)
    processed = apply_frame_shape_to_canvas(processed, frame_shape, border_color, border_width)

    if processed is None:
        raise RuntimeError("Internal processing error: processed image is None.")

    return processed


def slice_image(image: Image.Image, cols: int, rows: int):
    parts = []

    if image is None:
        raise RuntimeError("Internal slicing error: image is None.")

    for row in range(rows):
        for col in range(cols):
            x1 = col * TILE_SIZE
            y1 = row * TILE_SIZE
            box = (x1, y1, x1 + TILE_SIZE, y1 + TILE_SIZE)
            parts.append(image.crop(box))

    return parts


def save_image_parts(parts, output_dir: Path, log):
    output_names = [f"{i}.png" for i in range(1, len(parts) + 1)]
    sizes = []

    for name, part in zip(output_names, parts):
        output_path = output_dir / name

        if output_path.exists():
            output_path.unlink()

        part.save(output_path, format="PNG", optimize=True)
        sizes.append(output_path.stat().st_size)

    sizes_kb = [round(size / 1024, 2) for size in sizes]
    log(f"Sizes: {sizes_kb} KB")

    if not all(size <= MAX_SIZE_BYTES for size in sizes):
        oversized = [f"{name}: {round(size / 1024, 2)} KB" for name, size in zip(output_names, sizes) if size > MAX_SIZE_BYTES]
        raise RuntimeError(
            "Could not keep every image under 499 KB. Oversized files:\n" + "\n".join(oversized)
        )

    return sizes


def process_image(
    image_path: Path,
    grid: str,
    frame_shape: str,
    border_selection: str,
    border_custom_hex: str,
    border_width: int,
    overlay_selection: str,
    overlay_custom_hex: str,
    overlay_opacity: int,
    log
):
    if not image_path.exists():
        raise RuntimeError("Input file does not exist.")

    if image_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
        raise RuntimeError("Image mode only accepts .jpg, .jpeg, and .png files.")

    cols, rows = map(int, grid.lower().split("x"))

    validate_aspect_ratio(image_path, cols, rows)
    validate_frame_shape(frame_shape, cols, rows)

    border_color = resolve_color(border_selection, border_custom_hex)
    overlay_color = resolve_color(overlay_selection, overlay_custom_hex)

    output_dir = image_path.parent / f"eicon_image_output_{cols}x{rows}"
    output_dir.mkdir(exist_ok=True)

    log(f"Input: {image_path.name}")
    log("Mode: Image")
    log(f"Grid: {cols}x{rows}")
    log(f"Frame: {frame_shape}")
    log(f"Border: {border_selection}")
    log(f"Border thickness: {border_width}px")
    log(f"Overlay: {overlay_selection} at {overlay_opacity}%")
    log(f"Output folder: {output_dir}")
    log("")
    log("Aspect ratio validated.")
    log("Loading and processing image...")

    processed = load_processed_image(
        image_path,
        cols,
        rows,
        frame_shape,
        border_color,
        overlay_color,
        overlay_opacity,
        border_width
    )

    parts = slice_image(processed, cols, rows)
    sizes = save_image_parts(parts, output_dir, log)

    log("")
    log("DONE.")
    log("Generated PNG eicons.")
    log("")

    for i, size in enumerate(sizes, start=1):
        log(f"{i}.png: {round(size / 1024, 2)} KB")

    return output_dir


def process_input_file(
    input_path: Path,
    input_type: str,
    grid: str,
    frame_shape: str,
    border_selection: str,
    border_custom_hex: str,
    border_width: int,
    overlay_selection: str,
    overlay_custom_hex: str,
    overlay_opacity: int,
    log
):
    suffix = input_path.suffix.lower()

    if input_type == "GIF":
        if suffix != ".gif":
            raise RuntimeError("GIF mode only accepts .gif files.")

        return process_gif(
            input_path,
            grid,
            frame_shape,
            border_selection,
            border_custom_hex,
            border_width,
            overlay_selection,
            overlay_custom_hex,
            overlay_opacity,
            log
        )

    if input_type == "Image":
        if suffix not in {".jpg", ".jpeg", ".png"}:
            raise RuntimeError("Image mode only accepts .jpg, .jpeg, and .png files.")

        return process_image(
            input_path,
            grid,
            frame_shape,
            border_selection,
            border_custom_hex,
            border_width,
            overlay_selection,
            overlay_custom_hex,
            overlay_opacity,
            log
        )

    raise RuntimeError("Invalid mode selected. Choose GIF or Image.")


class EiconMakerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Eicon GIF / Image Maker")
        self.root.geometry("900x925")
        self.root.resizable(False, False)
        self.set_app_icon()

        self.input_path = tk.StringVar()
        self.input_type = tk.StringVar(value="GIF")
        self.grid_value = tk.StringVar(value="2x2")
        self.frame_shape = tk.StringVar(value="Square")

        self.border_color = tk.StringVar(value="none")
        self.border_hex = tk.StringVar(value="#a03cff")
        self.border_width = tk.StringVar(value=str(DEFAULT_BORDER_WIDTH))

        self.overlay_color = tk.StringVar(value="none")
        self.overlay_hex = tk.StringVar(value="#a03cff")
        self.overlay_opacity = tk.IntVar(value=25)
        self.overlay_opacity_text = tk.StringVar(value="25")
        self._syncing_opacity = False

        self.preset_name = tk.StringVar()
        self.selected_preset = tk.StringVar()
        self.presets = load_presets_file()

        self.is_processing = False

        self.setup_theme()
        self.build_ui()
        self.bind_color_updates()
        self.update_custom_hex_states()

        if DND_AVAILABLE:
            self.enable_drag_drop()

    def set_app_icon(self):
        """Set the Tkinter window/taskbar icon when the .ico file is available."""
        try:
            icon_path = resource_path(APP_ICON_FILENAME)

            if Path(icon_path).exists():
                self.root.iconbitmap(default=icon_path)
        except Exception:
            # Do not block the app if the icon file is missing or invalid.
            # The EXE icon is still controlled by PyInstaller's --icon argument.
            pass

    def setup_theme(self):
        BG = "#1e1f24"
        PANEL_2 = "#343742"
        TEXT = "#f2f2f2"
        MUTED = "#b8bcc8"
        ACCENT = "#7c5cff"
        ACCENT_HOVER = "#9278ff"
        ENTRY = "#181a20"

        self.root.configure(bg=BG)

        style = ttk.Style()
        style.theme_use("clam")

        style.configure(".", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=TEXT)

        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 22, "bold"))

        style.configure(
            "TLabelframe",
            background=BG,
            foreground=TEXT,
            bordercolor=PANEL_2,
            relief="solid"
        )

        style.configure(
            "TLabelframe.Label",
            background=BG,
            foreground=MUTED,
            font=("Segoe UI", 10, "bold")
        )

        style.configure(
            "TButton",
            background=PANEL_2,
            foreground=TEXT,
            borderwidth=0,
            focusthickness=0,
            padding=(10, 6)
        )

        style.map(
            "TButton",
            background=[
                ("active", "#3f4350"),
                ("pressed", "#4b5060"),
                ("disabled", "#25272e")
            ],
            foreground=[("disabled", "#777777")]
        )

        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground="#ffffff",
            borderwidth=0,
            padding=(14, 7),
            font=("Segoe UI", 10, "bold")
        )

        style.map(
            "Accent.TButton",
            background=[
                ("active", ACCENT_HOVER),
                ("pressed", "#684be8"),
                ("disabled", "#4a416e")
            ]
        )

        style.configure(
            "Help.TButton",
            background="#3a3d49",
            foreground=TEXT,
            borderwidth=0,
            padding=(4, 4)
        )

        style.map(
            "Help.TButton",
            background=[
                ("active", "#505464"),
                ("pressed", "#5b6072")
            ]
        )

        style.configure(
            "TEntry",
            fieldbackground=ENTRY,
            background=ENTRY,
            foreground=TEXT,
            insertcolor=TEXT,
            bordercolor=PANEL_2,
            lightcolor=PANEL_2,
            darkcolor=PANEL_2,
            padding=5
        )

        style.configure(
            "TCombobox",
            fieldbackground=ENTRY,
            background=PANEL_2,
            foreground=TEXT,
            arrowcolor=TEXT,
            bordercolor=PANEL_2,
            lightcolor=PANEL_2,
            darkcolor=PANEL_2,
            padding=5
        )

        style.map(
            "TCombobox",
            fieldbackground=[("readonly", ENTRY)],
            foreground=[("readonly", TEXT)],
            background=[("readonly", PANEL_2), ("active", "#3f4350")]
        )


        style.configure(
            "TSpinbox",
            fieldbackground=ENTRY,
            background=ENTRY,
            foreground=TEXT,
            insertcolor=TEXT,
            arrowcolor=TEXT,
            bordercolor=PANEL_2,
            lightcolor=PANEL_2,
            darkcolor=PANEL_2,
            selectbackground=ACCENT,
            selectforeground="#ffffff",
            padding=5
        )

        style.map(
            "TSpinbox",
            fieldbackground=[("readonly", ENTRY), ("disabled", "#25272e")],
            foreground=[("disabled", "#777777")],
            background=[("active", "#3f4350"), ("disabled", "#25272e")]
        )

        style.configure("Horizontal.TScale", background=BG, troughcolor=ENTRY)

    def help_button(self, parent, title, text):
        return ttk.Button(
            parent,
            text="?",
            width=3,
            style="Help.TButton",
            command=lambda: messagebox.showinfo(title, text)
        )

    def bind_color_updates(self):
        self.border_color.trace_add(
            "write",
            lambda *_: self.on_color_selection_changed(self.border_color, self.border_hex)
        )
        self.overlay_color.trace_add(
            "write",
            lambda *_: self.on_color_selection_changed(self.overlay_color, self.overlay_hex)
        )

    def on_color_selection_changed(self, selection_var, hex_var):
        self.sync_hex_from_selection(selection_var, hex_var)
        self.update_custom_hex_states()

    def sync_hex_from_selection(self, selection_var, hex_var):
        selected = selection_var.get()

        if selected in PRESET_COLORS and PRESET_COLORS[selected] not in (None, "custom"):
            hex_var.set(PRESET_COLORS[selected])

    def update_custom_hex_states(self):
        if hasattr(self, "border_hex_entry"):
            self.border_hex_entry.configure(
                state="normal" if self.border_color.get() == "custom" else "disabled"
            )

        if hasattr(self, "overlay_hex_entry"):
            self.overlay_hex_entry.configure(
                state="normal" if self.overlay_color.get() == "custom" else "disabled"
            )

    def build_ui(self):
        main = ttk.Frame(self.root, padding=18)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="Eicon GIF / Image Maker", style="Title.TLabel").pack(anchor="w")

        ttk.Label(
            main,
            text="Made by Kyara Star · Python tool · Shared as-is · No official support provided.",
            style="Muted.TLabel",
            wraplength=840
        ).pack(anchor="w", pady=(4, 8))

        ttk.Label(
            main,
            text=(
                "Disclaimer: This is not an official F-List tool. "
                "The HEX fields are optional. They are only editable and only used when the selected color is custom."
            ),
            style="Muted.TLabel",
            wraplength=840
        ).pack(anchor="w", pady=(0, 16))

        file_box = ttk.LabelFrame(main, text="Input File", padding=14)
        file_box.pack(fill="x")

        file_row = ttk.Frame(file_box)
        file_row.pack(fill="x")

        ttk.Label(file_row, text="Mode:").pack(side="left")
        self.input_type_combo = ttk.Combobox(
            file_row,
            textvariable=self.input_type,
            values=["GIF", "Image"],
            state="readonly",
            width=8
        )
        self.input_type_combo.pack(side="left", padx=(8, 10))
        self.input_type_combo.bind("<<ComboboxSelected>>", lambda _: self.on_input_type_changed())

        ttk.Entry(file_row, textvariable=self.input_path).pack(side="left", fill="x", expand=True)
        self.help_button(file_row, "Input File", HELP_TEXTS["input"]).pack(side="left", padx=(6, 0))
        ttk.Button(file_row, text="Browse", command=self.browse_input_file).pack(side="left", padx=(8, 0))

        hint = "Drag & drop a GIF, JPG, or PNG anywhere onto this window." if DND_AVAILABLE else "Drag & drop requires tkinterdnd2. Browse still works."
        ttk.Label(main, text=hint, style="Muted.TLabel").pack(anchor="w", pady=(8, 12))

        settings = ttk.LabelFrame(main, text="Settings", padding=14)
        settings.pack(fill="x")

        ttk.Label(settings, text="Grid:").grid(row=0, column=0, sticky="w")

        ttk.Combobox(
            settings,
            textvariable=self.grid_value,
            values=get_grid_options(),
            state="readonly",
            width=12
        ).grid(row=0, column=1, sticky="w", padx=(8, 4))

        self.help_button(settings, "Grid", HELP_TEXTS["grid"]).grid(row=0, column=2, sticky="w", padx=(0, 24))

        ttk.Label(settings, text="Frame:").grid(row=1, column=0, sticky="w", pady=(10, 0))

        ttk.Combobox(
            settings,
            textvariable=self.frame_shape,
            values=get_frame_options(),
            state="readonly",
            width=12
        ).grid(row=1, column=1, sticky="w", padx=(8, 4), pady=(10, 0))

        self.help_button(settings, "Frame Shape", HELP_TEXTS["frame"]).grid(row=1, column=2, sticky="w", padx=(0, 24), pady=(10, 0))

        ttk.Label(settings, text="Border:").grid(row=0, column=3, sticky="w")

        ttk.Combobox(
            settings,
            textvariable=self.border_color,
            values=list(PRESET_COLORS.keys()),
            state="readonly",
            width=12
        ).grid(row=0, column=4, sticky="w", padx=(8, 4))

        self.border_hex_entry = ttk.Entry(settings, textvariable=self.border_hex, width=10)
        self.border_hex_entry.grid(row=0, column=5, sticky="w")

        ttk.Button(
            settings,
            text="Pick",
            command=lambda: self.pick_custom_color(self.border_color, self.border_hex)
        ).grid(row=0, column=6, padx=(6, 4))

        self.help_button(settings, "Border", HELP_TEXTS["border"]).grid(row=0, column=7, sticky="w")

        ttk.Label(settings, text="Border thickness:").grid(row=1, column=3, sticky="w", pady=(10, 0))

        self.border_width_spinbox = tk.Spinbox(
            settings,
            from_=MIN_BORDER_WIDTH,
            to=MAX_BORDER_WIDTH,
            textvariable=self.border_width,
            width=6,
            bg="#181a20",
            fg="#f2f2f2",
            insertbackground="#ffffff",
            buttonbackground="#343742",
            buttonuprelief="flat",
            buttondownrelief="flat",
            highlightthickness=1,
            highlightbackground="#343742",
            highlightcolor="#7c5cff",
            relief="flat",
            selectbackground="#7c5cff",
            selectforeground="#ffffff",
            disabledbackground="#25272e",
            disabledforeground="#777777"
        )
        self.border_width_spinbox.grid(row=1, column=4, sticky="w", padx=(8, 4), pady=(10, 0))
        self.border_width_spinbox.bind("<Return>", lambda _: self.get_border_width())
        self.border_width_spinbox.bind("<FocusOut>", lambda _: self.get_border_width())

        ttk.Label(settings, text="px").grid(row=1, column=5, sticky="w", pady=(10, 0))

        overlay = ttk.LabelFrame(main, text="Overlay", padding=14)
        overlay.pack(fill="x", pady=(12, 0))

        ttk.Label(overlay, text="Overlay color:").grid(row=0, column=0, sticky="w")

        ttk.Combobox(
            overlay,
            textvariable=self.overlay_color,
            values=list(PRESET_COLORS.keys()),
            state="readonly",
            width=12
        ).grid(row=0, column=1, sticky="w", padx=(8, 4))

        self.overlay_hex_entry = ttk.Entry(overlay, textvariable=self.overlay_hex, width=10)
        self.overlay_hex_entry.grid(row=0, column=2, sticky="w")

        ttk.Button(
            overlay,
            text="Pick",
            command=lambda: self.pick_custom_color(self.overlay_color, self.overlay_hex)
        ).grid(row=0, column=3, padx=(6, 4))

        self.help_button(overlay, "Overlay", HELP_TEXTS["overlay"]).grid(row=0, column=4, sticky="w", padx=(0, 20))

        ttk.Label(overlay, text="Opacity:").grid(row=0, column=5, sticky="w")

        ttk.Scale(
            overlay,
            from_=0,
            to=100,
            variable=self.overlay_opacity,
            orient="horizontal",
            length=140,
            command=lambda _: self.update_opacity_label()
        ).grid(row=0, column=6, padx=(8, 4))

        self.opacity_entry = ttk.Entry(overlay, textvariable=self.overlay_opacity_text, width=5)
        self.opacity_entry.grid(row=0, column=7, sticky="w")
        self.opacity_entry.bind("<Return>", lambda _: self.apply_opacity_entry())
        self.opacity_entry.bind("<FocusOut>", lambda _: self.apply_opacity_entry())

        ttk.Label(overlay, text="%").grid(row=0, column=8, sticky="w", padx=(2, 0))

        self.help_button(overlay, "Overlay Opacity", HELP_TEXTS["opacity"]).grid(row=0, column=9, sticky="w", padx=(6, 0))

        presets_box = ttk.LabelFrame(main, text="Presets", padding=14)
        presets_box.pack(fill="x", pady=(12, 0))

        ttk.Label(presets_box, text="Preset name:").grid(row=0, column=0, sticky="w")

        ttk.Entry(
            presets_box,
            textvariable=self.preset_name,
            width=24
        ).grid(row=0, column=1, sticky="w", padx=(8, 8))

        ttk.Button(
            presets_box,
            text="Save / Update",
            command=self.save_current_preset
        ).grid(row=0, column=2, sticky="w", padx=(0, 8))

        ttk.Label(presets_box, text="Load preset:").grid(row=0, column=3, sticky="w", padx=(12, 0))

        self.preset_combo = ttk.Combobox(
            presets_box,
            textvariable=self.selected_preset,
            values=self.get_preset_names(),
            state="readonly",
            width=24
        )
        self.preset_combo.grid(row=0, column=4, sticky="w", padx=(8, 8))

        ttk.Button(
            presets_box,
            text="Load",
            command=self.load_selected_preset
        ).grid(row=0, column=5, sticky="w", padx=(0, 8))

        ttk.Button(
            presets_box,
            text="Delete",
            command=self.delete_selected_preset
        ).grid(row=0, column=6, sticky="w", padx=(0, 8))

        self.help_button(presets_box, "Presets", HELP_TEXTS["presets"]).grid(row=0, column=7, sticky="w")

        ttk.Label(
            presets_box,
            text=f"Saved in: {get_presets_path()}",
            style="Muted.TLabel",
            wraplength=820
        ).grid(row=1, column=0, columnspan=8, sticky="w", pady=(8, 0))

        crop_box = ttk.LabelFrame(main, text="Need to crop your file first?", padding=14)
        crop_box.pack(fill="x", pady=(12, 0))

        ttk.Label(
            crop_box,
            text=(
                "If your GIF/image has the wrong aspect ratio, crop it first. "
                "For example: 2x2 needs 1:1, 3x2 needs 3:2, 1x3 needs 1:3."
            ),
            style="Muted.TLabel",
            wraplength=690
        ).pack(side="left", fill="x", expand=True)

        ttk.Button(
            crop_box,
            text="EZGIF crop guide",
            command=lambda: messagebox.showinfo("EZGIF Crop Guide", HELP_TEXTS["ezgif"])
        ).pack(side="left", padx=(12, 0))

        actions = ttk.Frame(main)
        actions.pack(fill="x", pady=(16, 10))

        self.process_btn = ttk.Button(
            actions,
            text="Generate Eicons",
            command=self.start_processing,
            style="Accent.TButton"
        )
        self.process_btn.pack(side="left")

        ttk.Button(actions, text="Clear Log", command=self.clear_log).pack(side="left", padx=(8, 0))

        log_frame = ttk.LabelFrame(main, text="Log", padding=8)
        log_frame.pack(fill="both", expand=True)

        self.log_box = tk.Text(
            log_frame,
            height=16,
            wrap="word",
            state="disabled",
            bg="#15171d",
            fg="#e8e8e8",
            insertbackground="#ffffff",
            selectbackground="#7c5cff",
            selectforeground="#ffffff",
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=10,
            font=("Consolas", 9)
        )
        self.log_box.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_box.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_box.configure(yscrollcommand=scrollbar.set)

    def pick_custom_color(self, selection_var, hex_var):
        color = colorchooser.askcolor(initialcolor=hex_var.get())

        if color and color[1]:
            hex_var.set(color[1])
            selection_var.set("custom")
            self.update_custom_hex_states()

    def update_opacity_label(self):
        if self._syncing_opacity:
            return

        self._syncing_opacity = True
        self.overlay_opacity_text.set(str(int(float(self.overlay_opacity.get()))))
        self._syncing_opacity = False

    def apply_opacity_entry(self):
        if self._syncing_opacity:
            return

        raw_value = self.overlay_opacity_text.get().strip().replace("%", "")

        try:
            value = int(float(raw_value))
        except ValueError:
            value = self.overlay_opacity.get()

        value = max(0, min(100, value))

        self._syncing_opacity = True
        self.overlay_opacity.set(value)
        self.overlay_opacity_text.set(str(value))
        self._syncing_opacity = False

    def get_border_width(self) -> int:
        value = normalize_border_width(self.border_width.get())
        self.border_width.set(str(value))
        return value

    def get_current_config(self) -> dict:
        self.apply_opacity_entry()

        return {
            "input_type": self.input_type.get(),
            "grid": self.grid_value.get(),
            "frame_shape": self.frame_shape.get(),
            "border_color": self.border_color.get(),
            "border_hex": self.border_hex.get(),
            "border_width": self.get_border_width(),
            "overlay_color": self.overlay_color.get(),
            "overlay_hex": self.overlay_hex.get(),
            "overlay_opacity": int(self.overlay_opacity.get()),
        }

    def apply_config(self, config: dict):
        input_type = config.get("input_type", "GIF")
        grid = config.get("grid", "2x2")
        frame_shape = config.get("frame_shape", "Square")
        border_color = config.get("border_color", "none")
        border_hex = config.get("border_hex", "#a03cff")
        border_width = config.get("border_width", DEFAULT_BORDER_WIDTH)
        overlay_color = config.get("overlay_color", "none")
        overlay_hex = config.get("overlay_hex", "#a03cff")
        overlay_opacity = config.get("overlay_opacity", 25)

        if input_type not in {"GIF", "Image"}:
            input_type = "GIF"

        if grid not in get_grid_options():
            grid = "2x2"

        if frame_shape not in get_frame_options():
            frame_shape = "Square"

        if border_color not in PRESET_COLORS:
            border_color = "none"

        if overlay_color not in PRESET_COLORS:
            overlay_color = "none"

        try:
            overlay_opacity = int(float(overlay_opacity))
        except (TypeError, ValueError):
            overlay_opacity = 25

        overlay_opacity = max(0, min(100, overlay_opacity))

        self.input_type.set(input_type)
        self.grid_value.set(grid)
        self.frame_shape.set(frame_shape)
        self.border_color.set(border_color)
        self.border_hex.set(str(border_hex))
        self.border_width.set(str(normalize_border_width(border_width)))
        self.overlay_color.set(overlay_color)
        self.overlay_hex.set(str(overlay_hex))
        self.overlay_opacity.set(overlay_opacity)
        self.overlay_opacity_text.set(str(overlay_opacity))
        self.update_custom_hex_states()

    def get_preset_names(self):
        return sorted(self.presets.keys(), key=str.lower)

    def refresh_preset_combo(self):
        if hasattr(self, "preset_combo"):
            self.preset_combo.configure(values=self.get_preset_names())

    def save_current_preset(self):
        name = self.preset_name.get().strip()

        if not name:
            messagebox.showerror("Missing preset name", "Write a preset name before saving.")
            return

        self.presets[name] = self.get_current_config()

        try:
            save_presets_file(self.presets)
        except Exception as e:
            messagebox.showerror("Preset save error", f"Could not save preset file:\n{e}")
            return

        self.selected_preset.set(name)
        self.refresh_preset_combo()
        messagebox.showinfo("Preset saved", f"Preset saved as:\n{name}\n\nFile:\n{get_presets_path()}")

    def load_selected_preset(self):
        name = self.selected_preset.get().strip()

        if not name:
            messagebox.showerror("No preset selected", "Choose a preset from the dropdown first.")
            return

        config = self.presets.get(name)

        if not isinstance(config, dict):
            messagebox.showerror("Preset not found", "That preset no longer exists.")
            self.refresh_preset_combo()
            return

        self.apply_config(config)
        self.preset_name.set(name)
        messagebox.showinfo("Preset loaded", f"Preset loaded:\n{name}")

    def delete_selected_preset(self):
        name = self.selected_preset.get().strip()

        if not name:
            messagebox.showerror("No preset selected", "Choose a preset from the dropdown first.")
            return

        if name not in self.presets:
            messagebox.showerror("Preset not found", "That preset no longer exists.")
            self.refresh_preset_combo()
            return

        confirmed = messagebox.askyesno(
            "Delete preset",
            f"Delete preset '{name}'?"
        )

        if not confirmed:
            return

        del self.presets[name]

        try:
            save_presets_file(self.presets)
        except Exception as e:
            messagebox.showerror("Preset delete error", f"Could not update preset file:\n{e}")
            return

        self.selected_preset.set("")
        self.refresh_preset_combo()
        messagebox.showinfo("Preset deleted", f"Preset deleted:\n{name}")

    def enable_drag_drop(self):
        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind("<<Drop>>", self.on_drop)

    def on_drop(self, event):
        parts = self.root.tk.splitlist(event.data)
        self.input_path.set(str(Path(parts[0])))

    def browse_input_file(self):
        if self.input_type.get() == "Image":
            title = "Select Image"
            filetypes = [("Image files", "*.jpg *.jpeg *.png"), ("JPG files", "*.jpg *.jpeg"), ("PNG files", "*.png")]
        else:
            title = "Select GIF"
            filetypes = [("GIF files", "*.gif")]

        file_path = filedialog.askopenfilename(
            title=title,
            filetypes=filetypes
        )

        if file_path:
            self.input_path.set(file_path)

    def on_input_type_changed(self):
        current_path = self.input_path.get().strip()
        if not current_path:
            return

        suffix = Path(current_path).suffix.lower()

        if self.input_type.get() == "GIF" and suffix != ".gif":
            self.log(f"Mode changed to GIF. Current file is not a GIF: {current_path}")

        if self.input_type.get() == "Image" and suffix not in {".jpg", ".jpeg", ".png"}:
            self.log(f"Mode changed to Image. Current file is not JPG or PNG: {current_path}")

    def log(self, message):
        self.root.after(0, self._log_safe, message)

    def _log_safe(self, message):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def start_processing(self):
        if self.is_processing:
            return

        path_text = self.input_path.get().strip()

        if not path_text:
            messagebox.showerror("Missing file", "Please select or drag a file first.")
            return

        self.apply_opacity_entry()
        border_width = self.get_border_width()

        self.is_processing = True
        self.process_btn.configure(state="disabled")
        self.clear_log()

        thread = threading.Thread(
            target=self.processing_worker,
            args=(
                Path(path_text),
                self.input_type.get(),
                self.grid_value.get(),
                self.frame_shape.get(),
                self.border_color.get(),
                self.border_hex.get(),
                border_width,
                self.overlay_color.get(),
                self.overlay_hex.get(),
                int(self.overlay_opacity.get()),
            ),
            daemon=True
        )
        thread.start()

    def processing_worker(
        self,
        input_path,
        input_type,
        grid,
        frame_shape,
        border_selection,
        border_custom_hex,
        border_width,
        overlay_selection,
        overlay_custom_hex,
        overlay_opacity
    ):
        try:
            output_dir = process_input_file(
                input_path,
                input_type,
                grid,
                frame_shape,
                border_selection,
                border_custom_hex,
                border_width,
                overlay_selection,
                overlay_custom_hex,
                overlay_opacity,
                self.log
            )

            self.root.after(
                0,
                lambda: messagebox.showinfo(
                    "Done",
                    f"Eicons generated successfully:\n{output_dir}"
                )
            )

        except Exception as e:
            error_message = str(e)
            self.log("")
            self.log(f"ERROR: {error_message}")
            self.root.after(0, lambda msg=error_message: messagebox.showerror("Error", msg))

        finally:
            self.is_processing = False
            self.root.after(0, lambda: self.process_btn.configure(state="normal"))


if __name__ == "__main__":
    if DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()

    app = EiconMakerApp(root)
    root.mainloop()