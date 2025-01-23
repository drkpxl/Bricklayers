# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
#
import re
import sys
import logging
import os
import argparse

def detect_printer_type(gcode_lines):
    """Detect printer type based on G-code features"""
    for i, line in enumerate(gcode_lines):
        if "; FEATURE:" in line:
            return "bambu"
        elif ";TYPE:" in line:
            return "prusa"
    return "prusa"

def get_z_height_from_comment(line):
    """Extract Z height from comment if present"""
    if "; Z_HEIGHT:" in line:
        match = re.search(r'; Z_HEIGHT: ([\d.]+)', line)
        if match:
            return float(match.group(1))
    return None

def process_gcode(input_file, layer_height, extrusion_multiplier):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_file_path = os.path.join(script_dir, "brick_layer_log.txt")
    logging.basicConfig(
        filename=log_file_path,
        level=logging.INFO,
        format="%(asctime)s - %(message)s"
    )

    current_layer = 0
    current_z = 0.0
    in_inner_wall = False
    segment_count = 0
    last_was_travel = False
    in_object = False
    
    logging.info(f"Settings: Layer height={layer_height}mm, Multiplier={extrusion_multiplier}")

    with open(input_file, 'r') as infile:
        lines = infile.readlines()

    printer_type = detect_printer_type(lines)
    logging.info(f"Detected printer type: {printer_type}")
    modified_lines = []
    
    for i, line in enumerate(lines):
        # Track object printing sections
        if "M624" in line:
            in_object = True
            segment_count = 0
        elif "M625" in line:
            in_object = False
            if in_inner_wall:
                modified_lines.append(f"G1 Z{current_z:.3f} F1200 ; Reset Z at object end\n")
                in_inner_wall = False

        # Layer change detection
        if "; CHANGE_LAYER" in line:
            z_height = get_z_height_from_comment(lines[i + 1]) if i + 1 < len(lines) else None
            if z_height is not None:
                current_z = z_height
                current_layer += 1
                segment_count = 0
                logging.info(f"Layer {current_layer} at Z={current_z}")

        if in_object:
            # Feature detection
            if "; FEATURE:" in line:
                if in_inner_wall:
                    modified_lines.append(f"G1 Z{current_z:.3f} F1200 ; Reset Z\n")
                    in_inner_wall = False
                
                if "; FEATURE: Inner wall" in line:
                    in_inner_wall = True
                    segment_count = 0
                    logging.info("Inner wall start")
                else:
                    in_inner_wall = False

            # Process inner wall moves
            if in_inner_wall and line.startswith("G1"):
                is_travel = "F" in line and not "E" in line
                is_extrusion = "E" in line
                
                # New segment starts after a travel move
                if is_extrusion and last_was_travel:
                    segment_count += 1
                    shift_up = (segment_count + current_layer) % 2 == 1
                    
                    if shift_up:
                        adjusted_z = current_z + layer_height
                        modified_lines.append(f"G1 Z{adjusted_z:.3f} F1200 ; Shift up\n")
                        # Modify extrusion
                        e_match = re.search(r'E([-\d.]+)', line)
                        if e_match:
                            e_value = float(e_match.group(1))
                            new_e_value = e_value * extrusion_multiplier
                            line = re.sub(r'E[-\d.]+', f'E{new_e_value:.5f}', line.strip())
                            line += " ; Adjusted extrusion\n"
                            logging.info(f"Segment {segment_count}: shifted up with adjusted extrusion")
                    else:
                        modified_lines.append(f"G1 Z{current_z:.3f} F1200 ; Base height\n")
                        logging.info(f"Segment {segment_count}: base height")
                
                last_was_travel = is_travel

        modified_lines.append(line)

    with open(input_file, 'w') as outfile:
        outfile.writelines(modified_lines)
        
    logging.info(f"Processing complete: {current_layer} layers processed")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Brick Layer G-code processor")
    parser.add_argument("input_file", help="Input G-code file path")
    parser.add_argument("-layerHeight", type=float, default=0.2, help="Layer height (mm)")
    parser.add_argument("-extrusionMultiplier", type=float, default=1.5, help="Extrusion multiplier")
    args = parser.parse_args()

    process_gcode(args.input_file, args.layerHeight, args.extrusionMultiplier)
