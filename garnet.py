#!/usr/bin/env python3

import gi
gi.require_version('Gimp', '3.0')
from gi.repository import Gimp
gi.require_version('GimpUi', '3.0')
from gi.repository import GimpUi
gi.require_version('Gegl', '0.4')
from gi.repository import Gegl
from gi.repository import GObject
from gi.repository import GLib
from gi.repository import Gio
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

import colorsys
import sys
import random
import json
import os
import math

# Minimum diameter threshold in micrometers
MIN_DIAMETER_UM = 75.0
# Minimum area for a circle with diameter MIN_DIAMETER_UM
MIN_AREA_UM2 = math.pi * (MIN_DIAMETER_UM / 2) ** 2


def export_image_to_pngs(image, output_dir, layer_name=None):
    """Export a layer and all vector paths as PNG masks from an already-open image.

    In addition to PNG exports, also write a YOLO-seg label file (image.txt)
    containing polygon coordinates derived directly from the GIMP Paths (vectors).
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    # Export the requested layer (or first layer if no name given)
    layers = image.get_layers()
    if layers:
        if layer_name:
            # Find layer by name
            for layer in layers:
                if layer.get_name() == layer_name:
                    image_file = Gio.File.new_for_path(os.path.join(output_dir, "image.png"))
                    Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, image, image_file, None)
                    break
        else:
            # Use first layer
            layer = layers[0]
            image_file = Gio.File.new_for_path(os.path.join(output_dir, "image.png"))
            Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, image, image_file, None)

    # Prepare YOLO segmentation labels (vectors exported directly as polygons)
    img_w, img_h = image.get_width(), image.get_height()
    yolo_lines = []  # one line per polygon: "class x1 y1 x2 y2 ..." (normalized)

    # Export each vector path as a mask, and gather polygons for YOLO labels
    paths = image.get_paths()
    for i, v in enumerate(paths):
        # Build YOLO polygons from path strokes
        try:
            strokes = v.get_strokes()
        except Exception:
            strokes = []
        for stroke_id in strokes:
            try:
                coords, closed = v.stroke_interpolate(stroke_id, 2.0)  # precision ~2px
            except Exception:
                continue
            # Expect coords as [x0, y0, x1, y1, ...]
            if not coords or len(coords) < 6:
                continue
            if not closed:
                # Skip open strokes for YOLO polygons
                continue
            # Normalize and write line
            it = iter(coords)
            xy = []
            for x, y in zip(it, it):
                # Guard against zero dimension
                nx = (x / img_w) if img_w else 0.0
                ny = (y / img_h) if img_h else 0.0
                xy.append(nx)
                xy.append(ny)
            if len(xy) >= 6:
                # Single-class default: 0
                line = "0 " + " ".join(f"{v:.6f}" for v in xy)
                yolo_lines.append(line)

        # Create a new grayscale image for the mask
        mask_image = Gimp.Image.new(img_w, img_h, Gimp.ImageBaseType.GRAY)

        # Create a layer filled with black
        mask_layer = Gimp.Layer.new(mask_image, "mask",
                                      image.get_width(), image.get_height(),
                                      Gimp.ImageType.GRAY_IMAGE,
                                      100, Gimp.LayerMode.NORMAL)
        mask_image.insert_layer(mask_layer, None, 0)
        Gimp.context_set_foreground(Gegl.Color.new("black"))
        mask_layer.edit_fill(Gimp.FillType.FOREGROUND)

        # Create a new path in the mask image with the same strokes
        new_path = Gimp.Path.new(mask_image, v.get_name())
        mask_image.insert_path(new_path, None, 0)

        # Copy all strokes from the original path into mask image path
        try:
            strokes = v.get_strokes()
        except Exception:
            strokes = []
        for stroke_id in strokes:
            try:
                stroke_type, controlpoints, closed = v.stroke_get_points(stroke_id)
                new_path.stroke_new_from_points(stroke_type, controlpoints, closed)
            except Exception:
                # Skip strokes we fail to copy
                continue

        # Convert path to selection in the mask image
        Gimp.Selection.none(mask_image)
        mask_image.select_item(Gimp.ChannelOps.REPLACE, new_path)

        # Fill the selection with white
        Gimp.context_set_foreground(Gegl.Color.new("white"))
        mask_layer.edit_fill(Gimp.FillType.FOREGROUND)

        # Clear selection and export
        Gimp.Selection.none(mask_image)
        mask_file = Gio.File.new_for_path(os.path.join(output_dir, f"mask_{i}.png"))
        Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, mask_image, mask_file, None)

        # Clean up
        mask_image.delete()

    # Write YOLO labels next to the exported PNG image (same stem: image.txt)
    try:
        label_path = os.path.join(output_dir, "image.txt")
        with open(label_path, "w", encoding="utf-8") as f:
            f.write("\n".join(yolo_lines))
    except Exception:
        # Non-fatal if label writing fails
        pass


def extract_xcf_to_pngs(xcf_path, output_dir, layer_name=None):
    """Open a .xcf file, export one layer and all vector paths as PNG masks."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    file = Gio.File.new_for_path(xcf_path)
    image = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, file)

    export_image_to_pngs(image, output_dir, layer_name)


def get_global_config_path():
    """Get path to global configuration file"""
    config_dir = GLib.get_user_config_dir()
    return os.path.join(config_dir, 'garnet-plugin.json')


def get_project_config_path(image):
    """Get path to project-specific configuration file for saved XCF files"""
    try:
        file = image.get_file()
        if file:
            xcf_path = file.get_path()
            if xcf_path:
                # Change extension from .xcf to .json
                base_path = os.path.splitext(xcf_path)[0]
                return base_path + '.json'
    except Exception:
        pass
    return None


def save_scale(image, pixels, micrometers):
    """Save scale configuration to appropriate location based on image state"""
    scale_data = {
        'pixels': pixels,
        'micrometers': micrometers,
        'pixels_per_micrometer': pixels / micrometers if micrometers > 0 else 1.0
    }

    # Try to save to project-specific config for saved XCF files
    project_config_path = get_project_config_path(image)
    if project_config_path:
        with open(project_config_path, 'w') as f:
            json.dump(scale_data, f, indent=2)
        return

    # For unsaved images, save to global config with image ID
    global_config_path = get_global_config_path()
    config = {}
    if os.path.exists(global_config_path):
        try:
            with open(global_config_path, 'r') as f:
                config = json.load(f)
        except Exception:
            config = {}

    # Ensure 'scales' key exists
    if 'scales' not in config:
        config['scales'] = {}

    # Store under image ID
    image_id = str(image.get_id())
    config['scales'][image_id] = scale_data

    with open(global_config_path, 'w') as f:
        json.dump(config, f, indent=2)


def load_scale(image):
    """Load scale configuration from appropriate location, returns (pixels, micrometers, pixels_per_micrometer) or None"""
    # First check for project-specific config (for saved XCF files)
    project_config_path = get_project_config_path(image)
    if project_config_path and os.path.exists(project_config_path):
        try:
            with open(project_config_path, 'r') as f:
                config = json.load(f)
                return config['pixels'], config['micrometers'], config['pixels_per_micrometer']
        except Exception:
            pass

    # Check global config for unsaved images
    global_config_path = get_global_config_path()
    if os.path.exists(global_config_path):
        try:
            with open(global_config_path, 'r') as f:
                config = json.load(f)
                if 'scales' in config:
                    image_id = str(image.get_id())
                    if image_id in config['scales']:
                        scale_data = config['scales'][image_id]
                        return scale_data['pixels'], scale_data['micrometers'], scale_data['pixels_per_micrometer']
        except Exception:
            pass

    return None


def desaturate_color(color_rgb, amount=0.9):
    """Desaturate a color by blending it with gray"""
    gray = 0.5
    r = color_rgb[0] * (1 - amount) + gray * amount
    g = color_rgb[1] * (1 - amount) + gray * amount
    b = color_rgb[2] * (1 - amount) + gray * amount
    return (r, g, b)


def generate_colors(is_small_area=False):
    """Generate a pastel color for area and matching bright color for text"""
    hue = random.uniform(0, 360)
    pastel_saturation = random.uniform(0.3, 0.6)
    pastel_lightness = random.uniform(0.7, 0.9)
    pastel_r, pastel_g, pastel_b = colorsys.hls_to_rgb(hue/360, pastel_lightness, pastel_saturation)
    bright_saturation = random.uniform(0.8, 1.0)
    bright_lightness = random.uniform(0.2, 0.4)
    bright_r, bright_g, bright_b = colorsys.hls_to_rgb(hue/360, bright_lightness, bright_saturation)

    if is_small_area:
        pastel_r, pastel_g, pastel_b = desaturate_color((pastel_r, pastel_g, pastel_b))
        bright_r, bright_g, bright_b = desaturate_color((bright_r, bright_g, bright_b))

    return (pastel_r, pastel_g, pastel_b), (bright_r, bright_g, bright_b)


def find_selection_bounds(selection):
    """Find the actual bounds of selected pixels (returns x, y, width, height)"""
    selection_buffer = selection.get_buffer()
    sel_width = selection.get_width()
    sel_height = selection.get_height()
    min_x, min_y = sel_width, sel_height
    max_x, max_y = 0, 0
    chunk_size = 50
    found_pixels = False
    for start_y in range(0, sel_height, chunk_size):
        for start_x in range(0, sel_width, chunk_size):
            end_x = min(start_x + chunk_size, sel_width)
            end_y = min(start_y + chunk_size, sel_height)
            rect = Gegl.Rectangle.new(start_x, start_y, end_x - start_x, end_y - start_y)
            chunk_data = selection_buffer.get(rect, 1.0, None, Gegl.AbyssPolicy.NONE)
            for y_offset in range(end_y - start_y):
                for x_offset in range(end_x - start_x):
                    pixel_idx = y_offset * (end_x - start_x) + x_offset
                    if pixel_idx < len(chunk_data) and chunk_data[pixel_idx] > 0:
                        actual_x = start_x + x_offset
                        actual_y = start_y + y_offset
                        min_x = min(min_x, actual_x)
                        min_y = min(min_y, actual_y)
                        max_x = max(max_x, actual_x)
                        max_y = max(max_y, actual_y)
                        found_pixels = True
    if found_pixels:
        return min_x, min_y, max_x - min_x + 1, max_y - min_y + 1
    else:
        return 0, 0, sel_width, sel_height


def create_colored_layer(image, layer_name, color_rgb):
    """Create a new layer filled with the specified color"""
    new_layer = Gimp.Layer.new(image, layer_name,
                              image.get_width(), image.get_height(),
                              Gimp.ImageType.RGBA_IMAGE, 70.0, Gimp.LayerMode.NORMAL)
    image.insert_layer(new_layer, None, 0)
    color = Gegl.Color()
    color.set_rgba(color_rgb[0], color_rgb[1], color_rgb[2], 1.0)
    Gimp.context_set_foreground(color)
    new_layer.edit_fill(Gimp.FillType.FOREGROUND)
    return new_layer


def compute_selection_area(selection):
    """Count selected pixels in the current selection using 75% threshold"""
    sel_width = selection.get_width()
    sel_height = selection.get_height()
    rect = Gegl.Rectangle.new(0, 0, sel_width, sel_height)
    all_data = selection.get_buffer().get(rect, 1.0, None, Gegl.AbyssPolicy.NONE)
    return sum(1 for p in all_data if p >= 192)


def create_text_layer(image, text_content, x, y, layer_name, text_color=(1.0, 1.0, 1.0)):
    """Create a text layer with black outline for readability"""
    try:
        font = Gimp.context_get_font()
        white_color = Gegl.Color()
        white_color.set_rgba(1.0, 1.0, 1.0, 1.0)
        Gimp.context_set_foreground(white_color)
        text_layer = Gimp.text_font(image, None, x, y, text_content, 0, True, 16, font)
        text_layer.set_name(layer_name)
        text_layer.set_justification(Gimp.TextJustification.CENTER)
        text_width = text_layer.get_width()
        text_height = text_layer.get_height()
        text_layer.set_offsets(x - text_width // 2, y - text_height // 2)
        image.select_item(Gimp.ChannelOps.REPLACE, text_layer)
        Gimp.context_set_stroke_method(Gimp.StrokeMethod.LINE)
        Gimp.context_set_line_width(3.0)
        Gimp.context_set_line_cap_style(Gimp.CapStyle.ROUND)
        Gimp.context_set_line_join_style(Gimp.JoinStyle.ROUND)
        black_color = Gegl.Color()
        black_color.set_rgba(0.0, 0.0, 0.0, 1.0)
        Gimp.context_set_foreground(black_color)
        text_layer.edit_stroke_selection()
        final_color = Gegl.Color()
        final_color.set_rgba(text_color[0], text_color[1], text_color[2], 1.0)
        Gimp.context_set_foreground(final_color)
        text_layer.edit_fill(Gimp.FillType.FOREGROUND)
        Gimp.Selection.none(image)
        return text_layer
    except Exception as e:
        Gimp.message(f"Text creation failed: {e}")
        return None


class GarnetPlugin(Gimp.PlugIn):
    def do_query_procedures(self):
        return ['garnet-paths-areas', 'garnet-get-scale', 'garnet-export-xcf']

    def do_create_procedure(self, name):
        if name == 'garnet-get-scale':
            procedure = Gimp.ImageProcedure.new(self, name,
                                                Gimp.PDBProcType.PLUGIN,
                                                self.run_get_scale, None)
            procedure.set_image_types('*')
            procedure.set_menu_label('Set Scale from Selection')
            procedure.set_icon_name(GimpUi.ICON_TOOL_MEASURE)
            procedure.add_menu_path('<Image>/Filters/Garnet/')
            procedure.set_documentation(
                'Set Scale from Selection',
                'Measures selection size and asks for real-world micrometers to set scale',
                name,
            )
            procedure.set_attribution('OG', 'OG', '2025')
            return procedure
        elif name == 'garnet-export-xcf':
            procedure = Gimp.ImageProcedure.new(self, name,
                                           Gimp.PDBProcType.PLUGIN,
                                           self.run_export_xcf, None)
            procedure.set_image_types('*')
            procedure.set_menu_label('Export XCF to PNGs')
            procedure.set_icon_name(GimpUi.ICON_DOCUMENT_SAVE)
            procedure.add_menu_path('<Image>/Filters/Garnet/')
            procedure.set_documentation(
                'Export XCF to PNGs',
                'Export a layer and all vector paths as PNG masks from an XCF file',
                name,
            )
            procedure.set_attribution('OG', 'OG', '2025')

            # Add arguments for non-interactive mode
            procedure.add_string_argument("xcf-path", "XCF file path",
                                         "Path to the XCF file to export",
                                         "", GObject.ParamFlags.READWRITE)
            procedure.add_string_argument("output-dir", "Output directory",
                                         "Directory where PNG files will be saved",
                                         "", GObject.ParamFlags.READWRITE)
            procedure.add_string_argument("layer-name", "Layer name",
                                         "Name of layer to export (empty for first layer)",
                                         "", GObject.ParamFlags.READWRITE)

            return procedure
        elif name == 'garnet-paths-areas':
            procedure = Gimp.ImageProcedure.new(self, name,
                                                Gimp.PDBProcType.PLUGIN,
                                                self.run_paths_areas, None)
            procedure.set_image_types('*')
            procedure.set_menu_label('Compute Path Areas')
            procedure.set_icon_name(GimpUi.ICON_TOOL_MEASURE)
            procedure.add_menu_path('<Image>/Filters/Garnet/')
            procedure.set_documentation(
                'Compute Path Areas',
                'Measures pixel area for each path and creates colored layers with labeled text overlays',
                name,
            )
            procedure.set_attribution('OG', 'OG', '2025')
            return procedure

    def do_set_i18n(self, procname):
        return False

    def run_export_xcf(self, procedure, run_mode, image, drawables, config, run_data):
        # Try to get arguments from config for non-interactive mode
        xcf_path = None
        output_dir = None
        layer_name = None

        try:
            xcf_path = config.get_property('xcf-path')
            output_dir = config.get_property('output-dir')
            layer_name = config.get_property('layer-name')
        except:
            pass

        # If arguments are provided (non-interactive/batch mode), use them directly
        if xcf_path and output_dir:
            # Strip layer_name and convert empty string to None
            if layer_name:
                layer_name = layer_name.strip() or None

            try:
                extract_xcf_to_pngs(xcf_path, output_dir, layer_name)
                if layer_name:
                    Gimp.message(f"Successfully exported layer '{layer_name}' and vector paths to {output_dir}")
                else:
                    Gimp.message(f"Successfully exported first layer and vector paths to {output_dir}")
                return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())
            except Exception as e:
                error_msg = f"Export failed: {str(e)}"
                error = GLib.Error.new_literal(Gimp.PlugIn.error_quark(), error_msg, 0)
                return procedure.new_return_values(Gimp.PDBStatusType.EXECUTION_ERROR, error)

        # Interactive mode - show dialog
        GimpUi.init('garnet-export-xcf')

        dialog = GimpUi.Dialog(use_header_bar=True,
                               title='Export XCF to PNGs',
                               role='garnet-export-xcf')
        dialog.add_button('_Cancel', Gtk.ResponseType.CANCEL)
        dialog.add_button('_Export', Gtk.ResponseType.OK)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        dialog.get_content_area().add(vbox)

        # In GUI mode, use the currently open image
        info_label = Gtk.Label(label="Exporting current image")
        info_label.set_halign(Gtk.Align.START)
        vbox.pack_start(info_label, False, False, 0)

        # Output directory chooser
        output_label = Gtk.Label(label="Select output directory:")
        output_label.set_halign(Gtk.Align.START)
        vbox.pack_start(output_label, False, False, 0)

        output_chooser = Gtk.FileChooserButton(title="Select output directory")
        output_chooser.set_action(Gtk.FileChooserAction.SELECT_FOLDER)
        vbox.pack_start(output_chooser, False, False, 0)

        # Layer name entry
        layer_label = Gtk.Label(label="Layer name to export (leave empty for first layer):")
        layer_label.set_halign(Gtk.Align.START)
        vbox.pack_start(layer_label, False, False, 0)

        layer_entry = Gtk.Entry()
        layer_entry.set_placeholder_text("Leave empty to use first layer")
        vbox.pack_start(layer_entry, False, False, 0)

        dialog.show_all()

        if dialog.run() == Gtk.ResponseType.OK:
            output_dir = output_chooser.get_filename()
            layer_name = layer_entry.get_text().strip() or None

            if not output_dir:
                dialog.destroy()
                error_msg = "Please select an output directory!"
                error = GLib.Error.new_literal(Gimp.PlugIn.error_quark(), error_msg, 0)
                return procedure.new_return_values(Gimp.PDBStatusType.CALLING_ERROR, error)

            try:
                export_image_to_pngs(image, output_dir, layer_name)
                if layer_name:
                    Gimp.message(f"Successfully exported layer '{layer_name}' and vector paths to {output_dir}")
                else:
                    Gimp.message(f"Successfully exported first layer and vector paths to {output_dir}")
                dialog.destroy()
                return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())
            except Exception as e:
                dialog.destroy()
                error_msg = f"Export failed: {str(e)}"
                error = GLib.Error.new_literal(Gimp.PlugIn.error_quark(), error_msg, 0)
                return procedure.new_return_values(Gimp.PDBStatusType.EXECUTION_ERROR, error)

        dialog.destroy()
        return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

    def run_get_scale(self, procedure, run_mode, image, drawables, config, run_data):
        selection = image.get_selection()
        intersect, x, y, width, height = selection.mask_intersect()

        if not intersect:
            error_msg = "No selection found!\n\nPlease select the scale bar using the Fuzzy Select Tool first."
            error = GLib.Error.new_literal(Gimp.PlugIn.error_quark(), error_msg, 0)
            return procedure.new_return_values(Gimp.PDBStatusType.CALLING_ERROR, error)

        # Find actual bounds of selected pixels
        actual_x, actual_y, actual_width, actual_height = find_selection_bounds(selection)
        longer_side = max(actual_width, actual_height)
        Gimp.message(f"Selection size: {longer_side} pixels (longer side)")

        if run_mode == Gimp.RunMode.INTERACTIVE:
            GimpUi.init('garnet-get-scale')
            dialog = GimpUi.Dialog(use_header_bar=True,
                                   title='Set Scale',
                                   role='garnet-get-scale')
            dialog.add_button('_Cancel', Gtk.ResponseType.CANCEL)
            dialog.add_button('_OK', Gtk.ResponseType.OK)

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            vbox.set_margin_start(10)
            vbox.set_margin_end(10)
            vbox.set_margin_top(10)
            vbox.set_margin_bottom(10)
            dialog.get_content_area().add(vbox)

            label = Gtk.Label(label=f"Selection size: {longer_side} pixels\n\nEnter the real-world size in micrometers:")
            vbox.pack_start(label, False, False, 0)

            entry = Gtk.Entry()
            entry.set_text("100")
            vbox.pack_start(entry, False, False, 0)

            dialog.show_all()

            if dialog.run() == Gtk.ResponseType.OK:
                try:
                    micrometers = float(entry.get_text())
                    save_scale(image, longer_side, micrometers)
                    Gimp.message(f"Scale set: {longer_side} pixels = {micrometers} µm\n({longer_side/micrometers:.2f} pixels per micrometer)")
                    dialog.destroy()
                    return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())
                except ValueError:
                    dialog.destroy()
                    error_msg = "Invalid number entered!"
                    error = GLib.Error.new_literal(Gimp.PlugIn.error_quark(), error_msg, 0)
                    return procedure.new_return_values(Gimp.PDBStatusType.CALLING_ERROR, error)

            dialog.destroy()
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

    def run_paths_areas(self, procedure, run_mode, image, drawables, config, run_data):
        scale_config = load_scale(image)

        paths = image.get_paths()
        num_paths = len(paths)

        if num_paths == 0:
            error_msg = "No paths found in the image!\n\nYou need shapes saved in Paths for areas to be computed."
            error = GLib.Error.new_literal(Gimp.PlugIn.error_quark(), error_msg, 0)
            return procedure.new_return_values(Gimp.PDBStatusType.CALLING_ERROR, error)

        Gimp.message(f"Found {num_paths} paths in the image")

        if scale_config:
            pixels, micrometers, ppm = scale_config
            Gimp.message(f"Using scale: {pixels} px = {micrometers} µm ({ppm:.2f} px/µm)")
            Gimp.message(f"Minimum significant area: {MIN_AREA_UM2:.1f} µm² (circle diameter {MIN_DIAMETER_UM} µm)")

        # Start undo group so all operations can be undone with one Ctrl+Z
        image.undo_group_start()

        total_area = 0
        total_area_um2 = 0.0

        # Store label layer info to create them after all area layers
        label_layers_info = []

        for i, path in enumerate(paths):
            try:
                path_name = path.get_name()
            except AttributeError:
                path_name = f"Path {i+1}"

            Gimp.message(f"Processing path '{path_name}'...")

            image.select_item(Gimp.ChannelOps.REPLACE, path)
            selection = image.get_selection()
            intersect, x, y, width, height = selection.mask_intersect()

            if not intersect:
                Gimp.message(f"Path '{path_name}': No selection created")
                continue

            pixel_count = compute_selection_area(selection)
            total_area += pixel_count

            # Determine if area is significant
            is_small_area = False
            if scale_config:
                pixels, micrometers, ppm = scale_config
                area_um2 = (pixel_count / (ppm * ppm))
                total_area_um2 += area_um2
                is_small_area = area_um2 < MIN_AREA_UM2
                text_content = f"{pixel_count} px²\n{area_um2:.1f} µm²"
            else:
                text_content = f"{pixel_count} px²"

            pastel_color, bright_color = generate_colors(is_small_area)
            layer_name = f"Area_{path_name}"
            new_layer = create_colored_layer(image, layer_name, pastel_color)

            actual_x, actual_y, actual_w, actual_h = find_selection_bounds(selection)
            center_x = actual_x + (actual_w // 2)
            center_y = actual_y + (actual_h // 2)
            text_layer_name = f"Label_{path_name}"

            # Store label info to create later (after all area layers)
            label_layers_info.append({
                'text_content': text_content,
                'center_x': center_x,
                'center_y': center_y,
                'text_layer_name': text_layer_name,
                'bright_color': bright_color
            })

            if scale_config and is_small_area:
                Gimp.message(f"Path '{path_name}': {pixel_count} pixels ({area_um2:.1f} µm²) - BELOW THRESHOLD")
            else:
                Gimp.message(f"Path '{path_name}': {pixel_count} pixels (layer: {layer_name})")

        # Now create all label layers on top
        for label_info in label_layers_info:
            create_text_layer(image, label_info['text_content'],
                            label_info['center_x'], label_info['center_y'],
                            label_info['text_layer_name'], label_info['bright_color'])

        # End undo group
        image.undo_group_end()

        if scale_config:
            Gimp.message(f"Total area: {total_area} pixels ({total_area_um2:.1f} µm²)")
        else:
            Gimp.message(f"Total area: {total_area} pixels\n(Use 'Set Scale from Selection' to add micrometer measurements)")

        return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())


Gimp.main(GarnetPlugin.__gtype__, sys.argv)
