import sqlite3
import dotenv
import streamlit as st
import plotly.graph_objects as go
from typing import Any
import BreakerFrame
import EnclosureSizeSaver
import os
from dotenv import load_dotenv
from supabase import create_client, Client

dotenv.load_dotenv()

URL = os.getenv("SUPABASE_URL") or ""
KEY = os.getenv("SUPABASE_KEY") or ""
supabase: Client = create_client(URL, KEY)

Component_Frames = []
TRANOS_ENCLOSURES = []

BOTTOM_CLEARANCE = 200
TOP_CLEARANCE = 100
DISTRIBUTION_ROW_HEIGHT = 200
TERMINAL_BLOCK_ROW_HEIGHT = 200
CABLE_TERMINATION_ROW_HEIGHT = 100
BREAKER_GAP = 5



def load_Component_registry():
    try:
        response = supabase.table("breaker_instances").select("*").execute()
        return response.data  
    except Exception as e:
        pass
        return []


def load_Enclosure_registry():
    try:
        response = supabase.table("enclosure_sizes").select("*").execute()
        return response.data  
    except Exception as e:
        pass
        return []


def get_record_value(record, key, default: Any = 0):
    value = record.get(key, record.get(key.capitalize(), default))
    if isinstance(value, (int, float)):
        return value
    return default


def get_cover_plate_height(breaker_height):
    if breaker_height <= 100: return 100
    if breaker_height <= 200: return 200
    return 300


def build_breaker_rows(group_name, breakers, max_db_width):
    processed_rows = []
    height_map = {}

    for breaker in breakers:
        breaker_height = get_record_value(breaker, "height")
        height_map.setdefault(breaker_height, []).append(breaker)

    for breaker_height in sorted(height_map.keys(), reverse=True):
        current_row_breakers = []
        current_row_width = 0

        for breaker in height_map[breaker_height]:
            breaker_width = get_record_value(breaker, "width")
            breaker_width_with_gap = breaker_width + BREAKER_GAP

            if current_row_width + breaker_width_with_gap > max_db_width and current_row_breakers:
                processed_rows.append({
                    "cp_height": get_cover_plate_height(breaker_height),
                    "width": current_row_width,
                    "depth": max(get_record_value(item, "depth") for item in current_row_breakers),
                    "breakers": current_row_breakers,
                    "group": group_name,
                    "row_type": "breaker",
                    "label": None,
                })
                current_row_breakers = []
                current_row_width = 0

            current_row_breakers.append(breaker)
            current_row_width += breaker_width_with_gap

        if current_row_breakers:
            processed_rows.append({
                "cp_height": get_cover_plate_height(breaker_height),
                "width": current_row_width,
                "depth": max(get_record_value(item, "depth") for item in current_row_breakers),
                "breakers": current_row_breakers,
                "group": group_name,
                "row_type": "breaker",
                "label": None,
            })

    return processed_rows


def build_layout_units_for_enclosure(incoming_breakers, outgoing_breakers, row_width_limit, use_terminal_blocks):
    incoming_rows = build_breaker_rows("incoming", incoming_breakers, row_width_limit)
    outgoing_breaker_rows = build_breaker_rows("outgoing", outgoing_breakers, row_width_limit)

    incoming_units = []
    if use_terminal_blocks and incoming_rows:
        incoming_units.append(
            make_layout_unit([
                make_service_row(
                    TERMINAL_BLOCK_ROW_HEIGHT,
                    "incoming",
                    "terminal_blocks",
                    "Terminal Blocks",
                )
            ])
        )
    incoming_units.extend(make_layout_unit([row]) for row in incoming_rows)

    outgoing_units = []
    for row in outgoing_breaker_rows:
        unit_rows = [row]
        if not use_terminal_blocks:
            unit_rows.append(
                make_service_row(
                    CABLE_TERMINATION_ROW_HEIGHT,
                    "outgoing",
                    "cable_termination",
                    "Cable Termination Space",
                )
            )
        outgoing_units.append(make_layout_unit(unit_rows))

    return incoming_rows, outgoing_breaker_rows, incoming_units, outgoing_units


def get_3B_breaker_cubicle_width(breaker):
    breaker_type = str(get_record_value(breaker, "type", "")).lower()
    pole_count = int(get_record_value(breaker, "pole", 0) or 0)

    if breaker_type == "acb" and pole_count == 4:
        return 800
    if breaker_type == "acb" and pole_count == 3:
        return 600
    if breaker_type == "mccb":
        return 600
    return 600


def rotate_breaker_for_3B(breaker):
    rotated_breaker = dict(breaker)
    rotated_breaker["width"] = get_record_value(breaker, "height")
    rotated_breaker["height"] = get_record_value(breaker, "width")
    rotated_breaker["required_cubicle_width"] = get_3B_breaker_cubicle_width(breaker)
    return rotated_breaker


def build_3B_breaker_rows(group_name, breakers):
    processed_rows = []

    for breaker in breakers:
        rotated_breaker = rotate_breaker_for_3B(breaker)
        processed_rows.append({
            "cp_height": get_cover_plate_height(get_record_value(rotated_breaker, "height")),
            "width": get_record_value(rotated_breaker, "width") + BREAKER_GAP,
            "depth": get_record_value(rotated_breaker, "depth"),
            "breakers": [rotated_breaker],
            "group": group_name,
            "row_type": "breaker",
            "label": None,
            "required_cubicle_width": get_record_value(rotated_breaker, "required_cubicle_width", 600),
        })

    processed_rows.sort(key=lambda row: row["cp_height"], reverse=True)
    return processed_rows


def build_3B_layout_units(incoming_breakers, outgoing_breakers, use_terminal_blocks):
    incoming_rows = build_3B_breaker_rows("incoming", incoming_breakers)
    outgoing_rows = build_3B_breaker_rows("outgoing", outgoing_breakers)

    incoming_units = []
    if use_terminal_blocks and incoming_rows:
        incoming_units.append(
            make_layout_unit([
                make_service_row(
                    TERMINAL_BLOCK_ROW_HEIGHT,
                    "incoming",
                    "terminal_blocks",
                    "Terminal Blocks",
                )
            ])
        )
    incoming_units.extend(make_layout_unit([row]) for row in incoming_rows)

    outgoing_units = [make_layout_unit([row]) for row in outgoing_rows]
    return incoming_rows, outgoing_rows, incoming_units, outgoing_units


def get_3B_termination_cubicle_width(rows):
    paired_breakers = [
        breaker
        for row in rows
        for breaker in row.get("breakers", [])
    ]
    max_current = max((get_record_value(breaker, "max_current") for breaker in paired_breakers), default=0)
    return 600 if max_current < 400 else 800


def build_3B_lineup_cubicles(layout):
    breaker_cubicles = []
    lower_rows = layout.get("lower_rows", [])
    upper_rows = layout.get("upper_rows", [])

    for lower_group, upper_group in zip(lower_rows, upper_rows):
        if not lower_group and not upper_group:
            continue

        breaker_rows = lower_group + upper_group
        breaker_cubicles.append({
            "kind": "breaker",
            "label": f"Breaker Cubicle {len(breaker_cubicles) + 1}",
            "width": max((row.get("required_cubicle_width", 600) for row in breaker_rows if row.get("row_type") == "breaker"), default=600),
            "lower_rows": lower_group,
            "upper_rows": upper_group,
            "breaker_rows": breaker_rows,
        })

    lineup_cubicles = []
    termination_count = 0
    breaker_idx = 0

    while breaker_idx < len(breaker_cubicles):
        first_cubicle = breaker_cubicles[breaker_idx]

        if breaker_idx + 1 < len(breaker_cubicles):
            second_cubicle = breaker_cubicles[breaker_idx + 1]
            shared_rows = first_cubicle["breaker_rows"] + second_cubicle["breaker_rows"]
            lineup_cubicles.append(first_cubicle)
            breaker_idx += 2

            termination_count += 1
            lineup_cubicles.append({
                "kind": "termination",
                "label": f"Termination Cubicle {termination_count}",
                "width": get_3B_termination_cubicle_width(shared_rows),
                "lower_rows": [],
                "upper_rows": [],
            })
            lineup_cubicles.append(second_cubicle)
        else:
            lineup_cubicles.append(first_cubicle)
            shared_rows = first_cubicle["breaker_rows"]
            breaker_idx += 1
            termination_count += 1
            lineup_cubicles.append({
                "kind": "termination",
                "label": f"Termination Cubicle {termination_count}",
                "width": get_3B_termination_cubicle_width(shared_rows),
                "lower_rows": [],
                "upper_rows": [],
            })

    return lineup_cubicles, len(breaker_cubicles), termination_count


def find_common_3B_enclosure_details(enclosures, target_height, required_depth, required_widths):
    chosen_sections = {}
    section_depths = []

    for required_width in sorted(required_widths):
        matches = [
            enclosure for enclosure in enclosures
            if get_record_value(enclosure, "width") == required_width
            and get_record_value(enclosure, "height") == target_height
            and get_record_value(enclosure, "depth") >= required_depth
        ]
        if not matches:
            return None

        selected_section = min(matches, key=lambda enclosure: get_record_value(enclosure, "depth"))
        chosen_sections[required_width] = selected_section
        section_depths.append(get_record_value(selected_section, "depth"))

    return {
        "height": target_height,
        "depth": max(section_depths, default=required_depth),
        "section_widths": sorted(required_widths),
        "sections": chosen_sections,
    }


def make_service_row(cp_height, group_name, row_type, label):
    return {
        "cp_height": cp_height,
        "width": 0,
        "depth": 0,
        "breakers": [],
        "group": group_name,
        "row_type": row_type,
        "label": label,
    }


def make_layout_unit(rows):
    return {
        "rows": rows,
        "total_height": sum(row["cp_height"] for row in rows),
    }


def preferred_incoming_cubicles(num_cubicles):
    return list(range(num_cubicles))


def preferred_outgoing_cubicles(num_cubicles):
    if num_cubicles == 1:
        return [0]
    return [1, 0] + list(range(2, num_cubicles))


def pack_layout_units(units, num_cubicles, section_height, preferred_cubicles):
    if section_height < 0:
        return None, None

    bins = [section_height] * num_cubicles
    packing_plan = [[] for _ in range(num_cubicles)]
    used_heights = [0] * num_cubicles

    for unit in units:
        placed = False
        for cubicle_idx in preferred_cubicles(num_cubicles):
            if bins[cubicle_idx] >= unit["total_height"]:
                bins[cubicle_idx] -= unit["total_height"]
                packing_plan[cubicle_idx].extend(unit["rows"])
                used_heights[cubicle_idx] += unit["total_height"]
                placed = True
                break

        if not placed:
            return None, None

    return packing_plan, used_heights

def Options_selector_dict(Key, Selection_list):
    choice_list= [d[Key] for d in Selection_list if isinstance(d, dict) and Key in d]
    print("Choice List:", choice_list)
    return choice_list

def get_disp_component(selected_components):
    selected_models = set()
    Component_Frames = load_Component_registry()
    for item in selected_components:
        if isinstance(item, str):
            selected_models.add(item)
        elif isinstance(item, dict) and "model" in item:
            selected_models.add(item["model"])
    return [frame for frame in Component_Frames if isinstance(frame, dict) and frame.get("model") in selected_models]

def get_component(selected_components):
    Component_Frames = load_Component_registry()
    result = []

    for item in selected_components:
        # Extract model name
        if isinstance(item, str):
            model = item
        elif isinstance(item, dict) and "model" in item:
            model = item["model"]
        else:
            continue

        # Find matching frame and append
        for frame in Component_Frames:
            if isinstance(frame, dict) and frame.get("model") == model:
                result.append(frame)
                break  # stop after first match

    return result


def calculate_enclosure_2B(incoming_list, outgoing_list, use_terminal_blocks=False):
    TRANOS_ENCLOSURES = load_Enclosure_registry()
    all_breakers = incoming_list + outgoing_list
    required_min_depth = max((get_record_value(breaker, "depth") for breaker in all_breakers), default=0) + 50
    min_row_width_limit = max((get_record_value(breaker, "width") + BREAKER_GAP for breaker in all_breakers), default=0)
    
    for num_cubicles in range(1, 11): # Try up to 10 cubicles
        candidates = [
            enclosure for enclosure in TRANOS_ENCLOSURES
            if (get_record_value(enclosure, "width") - 150) >= min_row_width_limit
            and get_record_value(enclosure, "depth") >= required_min_depth
        ]
        candidates.sort(key=lambda item: (get_record_value(item, "height"), get_record_value(item, "width")))

        best_fit = None
        best_score = None

        for enclosure in candidates:
            row_width_limit = get_record_value(enclosure, "width") - 150
            incoming_rows, outgoing_breaker_rows, incoming_units, outgoing_units = build_layout_units_for_enclosure(
                incoming_list,
                outgoing_list,
                row_width_limit,
                use_terminal_blocks,
            )

            distribution_row = make_service_row(
                DISTRIBUTION_ROW_HEIGHT,
                "distribution",
                "distribution",
                "Distribution Space",
            )

            usable_height = get_record_value(enclosure, "height") - (
                BOTTOM_CLEARANCE + TOP_CLEARANCE + DISTRIBUTION_ROW_HEIGHT
            )
            if usable_height < 0:
                continue

            min_lower_height = 0
            if incoming_units:
                min_lower_height = max(unit["total_height"] for unit in incoming_units)

            for lower_section_height in range(int(min_lower_height), int(usable_height + 1), 100):
                incoming_plan, lower_used_heights = pack_layout_units(
                    incoming_units,
                    num_cubicles,
                    lower_section_height,
                    preferred_incoming_cubicles,
                )
                if incoming_plan is None:
                    continue

                upper_section_height = usable_height - lower_section_height
                outgoing_plan, upper_used_heights = pack_layout_units(
                    outgoing_units,
                    num_cubicles,
                    upper_section_height,
                    preferred_outgoing_cubicles,
                )
                if outgoing_plan is None:
                    continue

                aligned_lower_height = max(lower_used_heights or [], default=0)
                total_unused_height = sum(
                    max(aligned_lower_height - lower_used, 0) + max(upper_section_height - upper_used, 0)
                    for lower_used, upper_used in zip(lower_used_heights or [], upper_used_heights or [])
                )

                current_fit = {
                    "status": "Success",
                    "cubicles": num_cubicles,
                    "enclosure_used": enclosure,
                    "layout": {
                        "lower_rows": incoming_plan,
                        "upper_rows": outgoing_plan,
                        "distribution_row": distribution_row,
                        "lower_section_height": lower_section_height,
                        "upper_section_height": upper_section_height,
                        "aligned_lower_height": aligned_lower_height,
                        "lower_used_heights": lower_used_heights,
                        "upper_used_heights": upper_used_heights,
                    }
                }

                current_score = (
                    total_unused_height,
                    get_record_value(enclosure, "width"),
                    get_record_value(enclosure, "height"),
                )

                if best_score is None or current_score < best_score:
                    best_score = current_score
                    best_fit = current_fit

                break

        if best_fit is not None:
            return best_fit

    return {"status": "No Fit Found"}


def calculate_enclosure_3B(incoming_list, outgoing_list, use_terminal_blocks=False):
    TRANOS_ENCLOSURES = load_Enclosure_registry()
    all_breakers = incoming_list + outgoing_list
    required_min_depth = max((get_record_value(breaker, "depth") for breaker in all_breakers), default=0) + 50
    candidate_heights = sorted({
        get_record_value(enclosure, "height")
        for enclosure in TRANOS_ENCLOSURES
        if get_record_value(enclosure, "width") in {600, 800}
        and get_record_value(enclosure, "depth") >= required_min_depth
    })

    incoming_rows, outgoing_rows, incoming_units, outgoing_units = build_3B_layout_units(
        incoming_list,
        outgoing_list,
        use_terminal_blocks,
    )

    distribution_row = make_service_row(
        DISTRIBUTION_ROW_HEIGHT,
        "distribution",
        "distribution",
        "Distribution Space",
    )

    for num_breaker_cubicles in range(1, 11):
        best_fit = None
        best_score = None

        for enclosure_height in candidate_heights:
            usable_height = enclosure_height - (
                BOTTOM_CLEARANCE + TOP_CLEARANCE + DISTRIBUTION_ROW_HEIGHT
            )
            if usable_height < 0:
                continue

            min_lower_height = 0
            if incoming_units:
                min_lower_height = max(unit["total_height"] for unit in incoming_units)

            for lower_section_height in range(int(min_lower_height), int(usable_height + 1), 100):
                incoming_plan, lower_used_heights = pack_layout_units(
                    incoming_units,
                    num_breaker_cubicles,
                    lower_section_height,
                    preferred_incoming_cubicles,
                )
                if incoming_plan is None:
                    continue

                upper_section_height = usable_height - lower_section_height
                outgoing_plan, upper_used_heights = pack_layout_units(
                    outgoing_units,
                    num_breaker_cubicles,
                    upper_section_height,
                    preferred_outgoing_cubicles,
                )
                if outgoing_plan is None:
                    continue

                aligned_lower_height = max(lower_used_heights or [], default=0)
                base_layout = {
                    "lower_rows": incoming_plan,
                    "upper_rows": outgoing_plan,
                    "distribution_row": distribution_row,
                    "lower_section_height": lower_section_height,
                    "upper_section_height": upper_section_height,
                    "aligned_lower_height": aligned_lower_height,
                    "lower_used_heights": lower_used_heights,
                    "upper_used_heights": upper_used_heights,
                    "panel_form": "3B",
                }

                lineup_cubicles, breaker_cubicle_count, termination_cubicle_count = build_3B_lineup_cubicles(base_layout)
                required_widths = {cubicle["width"] for cubicle in lineup_cubicles}
                enclosure_details = find_common_3B_enclosure_details(
                    TRANOS_ENCLOSURES,
                    enclosure_height,
                    required_min_depth,
                    required_widths,
                )
                if enclosure_details is None:
                    continue

                total_lineup_width = sum(cubicle["width"] for cubicle in lineup_cubicles)
                total_unused_height = sum(
                    max(aligned_lower_height - lower_used, 0) + max(upper_section_height - upper_used, 0)
                    for lower_used, upper_used in zip(lower_used_heights or [], upper_used_heights or [])
                )

                current_fit = {
                    "status": "Success",
                    "cubicles": len(lineup_cubicles),
                    "breaker_cubicles": breaker_cubicle_count,
                    "termination_cubicles": termination_cubicle_count,
                    "enclosure_used": {
                        **enclosure_details,
                        "panel_form": "3B",
                        "total_width": total_lineup_width,
                    },
                    "layout": {
                        **base_layout,
                        "lineup_cubicles": lineup_cubicles,
                    }
                }

                current_score = (
                    total_unused_height,
                    total_lineup_width,
                    enclosure_height,
                )

                if best_score is None or current_score < best_score:
                    best_score = current_score
                    best_fit = current_fit

                break

        if best_fit is not None:
            return best_fit

    return {"status": "No Fit Found"}



def draw_cubicle_layout(packing_plan, enclosure_details):
    fig = go.Figure()
    enc_h = get_record_value(enclosure_details, "height", 2000)
    lower_section_height = packing_plan.get("aligned_lower_height", packing_plan.get("lower_section_height", 0))
    distribution_row = packing_plan.get("distribution_row", make_service_row(DISTRIBUTION_ROW_HEIGHT, "distribution", "distribution", "Distribution Space"))
    distribution_y0 = BOTTOM_CLEARANCE + lower_section_height
    distribution_y1 = distribution_y0 + distribution_row["cp_height"]
    upper_used_heights = packing_plan.get("upper_used_heights", [])

    def row_style(row):
        row_type = row.get("row_type", "breaker")
        if row_type == "distribution":
            return dict(line_color="DarkGoldenRod", fill_color="rgba(255, 236, 179, 0.7)")
        if row_type == "terminal_blocks":
            return dict(line_color="SeaGreen", fill_color="rgba(204, 255, 204, 0.7)")
        if row_type == "cable_termination":
            return dict(line_color="SandyBrown", fill_color="rgba(255, 228, 196, 0.7)")
        return dict(line_color="Gray", fill_color="rgba(240, 240, 240, 0.7)")

    def draw_row(row, x_offset, row_y0, row_y1, cubicle_width):
        cp_w = cubicle_width - 40
        style = row_style(row)

        fig.add_shape(
            type="rect",
            x0=x_offset + 20, y0=row_y0,
            x1=x_offset + 20 + cp_w, y1=row_y1,
            line=dict(color=style["line_color"], width=1, dash="dash"),
            fillcolor=style["fill_color"]
        )

        if row.get("label"):
            fig.add_annotation(
                x=x_offset + cubicle_width / 2,
                y=(row_y0 + row_y1) / 2,
                text=row["label"],
                showarrow=False,
                font=dict(size=12, color="DimGray")
            )

        total_breakers_w = sum(get_record_value(breaker, "width") + BREAKER_GAP for breaker in row["breakers"])
        current_x = x_offset + 20 + (cp_w - total_breakers_w) / 2 if row["breakers"] else x_offset + 20

        for breaker in row["breakers"]:
            breaker_width = get_record_value(breaker, "width")
            breaker_height = get_record_value(breaker, "height")
            breaker_depth = get_record_value(breaker, "depth")
            y_offset = (row["cp_height"] - breaker_height) / 2

            fig.add_shape(
                type="rect",
                x0=current_x, y0=row_y0 + y_offset,
                x1=current_x + breaker_width, y1=row_y0 + y_offset + breaker_height,
                line=dict(color="RoyalBlue", width=2),
                fillcolor="LightSkyBlue"
            )

            fig.add_trace(go.Scatter(
                x=[current_x + breaker_width / 2],
                y=[row_y0 + row["cp_height"] / 2],
                text=[f"<b>{breaker.get('model')}</b><br>W: {breaker_width}mm<br>H: {breaker_height}mm<br>D: {breaker_depth}mm"],
                mode="markers",
                marker=dict(opacity=0),
                hoverinfo="text",
                showlegend=False
            ))

            current_x += breaker_width + BREAKER_GAP

    gutter = 100
    lineup_cubicles = packing_plan.get("lineup_cubicles")

    if lineup_cubicles:
        current_x_offset = 0

        for cubicle in lineup_cubicles:
            cubicle_width = cubicle.get("width", 600)
            x_offset = current_x_offset

            fig.add_shape(
                type="rect",
                x0=x_offset, y0=0, x1=x_offset + cubicle_width, y1=enc_h,
                line=dict(color="Black", width=3),
                fillcolor="rgba(200, 200, 200, 0.1)"
            )

            fig.add_annotation(
                x=x_offset + cubicle_width / 2, y=enc_h + 50,
                text=cubicle.get("label", "Cubicle"),
                showarrow=False, font=dict(size=14, weight="bold")
            )

            if cubicle.get("kind") == "termination":
                fig.add_shape(
                    type="rect",
                    x0=x_offset + 20, y0=BOTTOM_CLEARANCE,
                    x1=x_offset + cubicle_width - 20, y1=enc_h - TOP_CLEARANCE,
                    line=dict(color="SandyBrown", width=1, dash="dash"),
                    fillcolor="rgba(255, 245, 230, 0.7)"
                )
                fig.add_annotation(
                    x=x_offset + cubicle_width / 2,
                    y=(BOTTOM_CLEARANCE + enc_h - TOP_CLEARANCE) / 2,
                    text="Cable Termination",
                    showarrow=False,
                    font=dict(size=12, color="SaddleBrown")
                )
            else:
                current_lower_y = BOTTOM_CLEARANCE
                for row in cubicle.get("lower_rows", []):
                    row_y0 = current_lower_y
                    row_y1 = current_lower_y + row["cp_height"]
                    draw_row(row, x_offset, row_y0, row_y1, cubicle_width)
                    current_lower_y += row["cp_height"]

                draw_row(distribution_row, x_offset, distribution_y0, distribution_y1, cubicle_width)

                upper_rows = cubicle.get("upper_rows", [])
                current_upper_y = distribution_y1 + sum(row["cp_height"] for row in upper_rows)
                for row in upper_rows:
                    row_y1 = current_upper_y
                    row_y0 = current_upper_y - row["cp_height"]
                    draw_row(row, x_offset, row_y0, row_y1, cubicle_width)
                    current_upper_y -= row["cp_height"]

            current_x_offset += cubicle_width + gutter
    else:
        enc_w = get_record_value(enclosure_details, "width", 800)

        for cubicle_idx, lower_rows in enumerate(packing_plan.get("lower_rows", [])):
            x_offset = cubicle_idx * (enc_w + gutter)

            fig.add_shape(
                type="rect",
                x0=x_offset, y0=0, x1=x_offset + enc_w, y1=enc_h,
                line=dict(color="Black", width=3),
                fillcolor="rgba(200, 200, 200, 0.1)"
            )

            fig.add_annotation(
                x=x_offset + enc_w / 2, y=enc_h + 50,
                text=f"Cubicle {cubicle_idx + 1}",
                showarrow=False, font=dict(size=14, weight="bold")
            )

            current_lower_y = BOTTOM_CLEARANCE
            for row in lower_rows:
                row_y0 = current_lower_y
                row_y1 = current_lower_y + row["cp_height"]
                draw_row(row, x_offset, row_y0, row_y1, enc_w)
                current_lower_y += row["cp_height"]

            draw_row(distribution_row, x_offset, distribution_y0, distribution_y1, enc_w)

            current_upper_y = distribution_y1 + (upper_used_heights[cubicle_idx] if cubicle_idx < len(upper_used_heights) else 0)
            for row in packing_plan.get("upper_rows", [[] for _ in packing_plan.get("lower_rows", [])])[cubicle_idx]:
                row_y1 = current_upper_y
                row_y0 = current_upper_y - row["cp_height"]
                draw_row(row, x_offset, row_y0, row_y1, enc_w)
                current_upper_y -= row["cp_height"]

    # Layout Adjustments
    fig.update_layout(
        title="Tranos Enclosure Layout",
        xaxis=dict(showgrid=False, zeroline=False, visible=False),
        yaxis=dict(scaleanchor="x", scaleratio=1, showgrid=False),
        height=800,
        margin=dict(l=20, r=20, t=60, b=20),
        template="plotly_white"
    )
    
    return fig

def render_enclosure_estimator_page():
    st.title("Enclosure Size Estimator")
    st.caption("Use the sidebar to switch between the estimator, enclosure saver, and breaker registry.")
   
    Component_Frames = load_Component_registry()
    panel_form = st.radio(
        "Select panel form",
        options=["Form 2B", "Form 3B"],
        horizontal=True,
    )
        
    selected_components1 = st.multiselect(
    "Choose incoming breakers",
    options=Options_selector_dict("model", Component_Frames),
    )

    Incoming_components = []

    for idx, comp in enumerate(selected_components1):
        qty1 = st.number_input(
            f"Quantity for {comp}",
            key=f"incoming_{idx}_{comp}",  # unique key
            min_value=1,
            step=1
        )
        Incoming_components.extend([comp] * qty1)

    # 4. Display Logic
    if Incoming_components:
             st.write("---")
             with st.expander(f"Components Details", expanded=True):
                 st.write(get_disp_component(Incoming_components))
    else:
           st.info("Select a breaker.")

    use_terminal_blocks = st.radio(
        "Will terminal blocks be used?",
        options=["No", "Yes"],
        horizontal=True,
    ) == "Yes"
    
    selected_components2 = st.multiselect(
    "Choose outgoing breakers",
    options=Options_selector_dict("model", Component_Frames),
    )

    Outgoing_components = []

    for idx, comp in enumerate(selected_components2):
        qty2 = st.number_input(
            f"Outgoing - Quantity for {comp}",
            key=f"outgoing_{idx}_{comp}",   # unique key
            min_value=1,
            step=1
        )
        Outgoing_components.extend([comp] * qty2)
    # 4. Display Logic
    if Outgoing_components:
            st.write("---")
            with st.expander(f"Components Details", expanded=True):
                st.write(get_disp_component(Outgoing_components))
    else:
            st.info("Select a breaker.")

    if st.button("Calculate Enclosure Size"):
            Selected_incoming = get_component(Incoming_components)
            Selected_outgoing = get_component(Outgoing_components)
            selected_enclosure = {
            }
            if panel_form == "Form 3B":
                Estimated_Enclosure = calculate_enclosure_3B(
                    Selected_incoming,
                    Selected_outgoing,
                    use_terminal_blocks=use_terminal_blocks,
                )
            else:
                Estimated_Enclosure = calculate_enclosure_2B(
                    Selected_incoming,
                    Selected_outgoing,
                    use_terminal_blocks=use_terminal_blocks,
                )
            Status = Estimated_Enclosure.get("status")
            Cubicle_Count = Estimated_Enclosure.get("cubicles")
            selected_enclosure = Estimated_Enclosure.get("enclosure_used")
            Panel_Layout = Estimated_Enclosure.get("layout")
            if Status == "Success":
                st.write(f"Calculation Status: {Status}")
                st.write(f"Recommended Tranos Enclosure: {selected_enclosure}")
                st.write(f"Number of Cubicles: {Cubicle_Count}")
                if panel_form == "Form 3B":
                    st.write(f"Breaker Cubicles: {Estimated_Enclosure.get('breaker_cubicles')}")
                    st.write(f"Termination Cubicles: {Estimated_Enclosure.get('termination_cubicles')}")
                fig = draw_cubicle_layout(Panel_Layout, selected_enclosure)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.error("Could not find a valid enclosure for these components.")


def main():
    pages = {
        "Enclosure Size Estimator": render_enclosure_estimator_page,
        "Enclosure Size Saver": EnclosureSizeSaver.main,
        "Circuit Breaker Registry": BreakerFrame.main,
    }

    st.sidebar.title("Navigation")
    selected_page = st.sidebar.radio("Go to", list(pages.keys()))
    pages[selected_page]()


if __name__ == "__main__":
    main()
