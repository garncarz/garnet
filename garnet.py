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


def get_scale_config_path():
    """Get path to scale configuration file"""
    config_dir = GLib.get_user_config_dir()
    garnet_dir = os.path.join(config_dir, 'GIMP', '3.0', 'plug-ins', 'garnet')
    os.makedirs(garnet_dir, exist_ok=True)
    return os.path.join(garnet_dir, 'scale_config.json')


def save_scale(pixels, micrometers):
    """Save scale configuration to JSON file"""
    config_path = get_scale_config_path()
    config = {
        'pixels': pixels,
        'micrometers': micrometers,
        'pixels_per_micrometer': pixels / micrometers if micrometers > 0 else 1.0
    }
    with open(config_path, 'w') as f:
        json.dump(config, f)


def load_scale():
    """Load scale configuration from JSON file, returns (pixels, micrometers, pixels_per_micrometer) or None"""
    config_path = get_scale_config_path()
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                return config['pixels'], config['micrometers'], config['pixels_per_micrometer']
        except Exception:
            return None
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
        return ['garnet-paths-areas', 'garnet-get-scale']

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
                    save_scale(longer_side, micrometers)
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
        scale_config = load_scale()

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
            text_layer = create_text_layer(image, text_content, center_x, center_y, text_layer_name, bright_color)

            if scale_config and is_small_area:
                Gimp.message(f"Path '{path_name}': {pixel_count} pixels ({area_um2:.1f} µm²) - BELOW THRESHOLD")
            else:
                Gimp.message(f"Path '{path_name}': {pixel_count} pixels (layer: {layer_name})")

        # End undo group
        image.undo_group_end()

        if scale_config:
            Gimp.message(f"Total area: {total_area} pixels ({total_area_um2:.1f} µm²)")
        else:
            Gimp.message(f"Total area: {total_area} pixels\n(Use 'Set Scale from Selection' to add micrometer measurements)")

        return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())


Gimp.main(GarnetPlugin.__gtype__, sys.argv)
