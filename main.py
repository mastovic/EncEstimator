import sqlite3
import streamlit as st
import plotly.graph_objects as go
import BreakerFrame
import EnclosureSizeSaver

Component_Frames = []
TRANOS_ENCLOSURES = []

BOTTOM_CLEARANCE = 200
TOP_CLEARANCE = 100
DISTRIBUTION_ROW_HEIGHT = 200
TERMINAL_BLOCK_ROW_HEIGHT = 200
CABLE_TERMINATION_ROW_HEIGHT = 100
BREAKER_GAP = 5



def load_Component_registry(db_path="breaker_instances.db"):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row 
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM breaker_instances")
    rows = cursor.fetchall()

    conn.close()

    return [dict(row) for row in rows]


def load_Enclosure_registry(db_path="Enclosure_sizes.db"):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM enclosure_sizes")
    rows = cursor.fetchall()

    conn.close()

    return [dict(row) for row in rows]


def get_record_value(record, key, default=0):
    return record.get(key, record.get(key.capitalize(), default))


def get_cover_plate_height(breaker_height):
    if breaker_height <= 200: return 200
    if breaker_height <= 300: return 300
    return 400


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


def preferred_incoming_cubicles(num_cubicles):
    return list(range(num_cubicles))


def preferred_outgoing_cubicles(num_cubicles):
    if num_cubicles == 1:
        return [0]
    return [1, 0] + list(range(2, num_cubicles))


def pack_rows(rows, num_cubicles, section_height, preferred_cubicles):
    if section_height < 0:
        return None

    bins = [section_height] * num_cubicles
    packing_plan = [[] for _ in range(num_cubicles)]

    for row in rows:
        placed = False
        for cubicle_idx in preferred_cubicles(num_cubicles):
            if bins[cubicle_idx] >= row["cp_height"]:
                bins[cubicle_idx] -= row["cp_height"]
                packing_plan[cubicle_idx].append(row)
                placed = True
                break

        if not placed:
            return None

    return packing_plan

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


def calculate_enclosure(incoming_list, outgoing_list, use_terminal_blocks=False):
    TRANOS_ENCLOSURES = load_Enclosure_registry()
    
    # 1. Determine the absolute maximum width available in your registry
    MAX_DB_WIDTH = max((get_record_value(e, "width", 800) for e in TRANOS_ENCLOSURES), default=800) - 150 # -150 for margins

    incoming_rows = build_breaker_rows("incoming", incoming_list, MAX_DB_WIDTH)
    outgoing_breaker_rows = build_breaker_rows("outgoing", outgoing_list, MAX_DB_WIDTH)

    if use_terminal_blocks and incoming_rows:
        incoming_rows.append(
            make_service_row(
                TERMINAL_BLOCK_ROW_HEIGHT,
                "incoming",
                "terminal_blocks",
                "Terminal Blocks",
            )
        )

    outgoing_rows = []
    for row in outgoing_breaker_rows:
        outgoing_rows.append(row)
        if not use_terminal_blocks:
            outgoing_rows.append(
                make_service_row(
                    CABLE_TERMINATION_ROW_HEIGHT,
                    "outgoing",
                    "cable_termination",
                    "Cable Termination Space",
                )
            )

    distribution_row = make_service_row(
        DISTRIBUTION_ROW_HEIGHT,
        "distribution",
        "distribution",
        "Distribution Space",
    )

    breaker_rows = incoming_rows + outgoing_breaker_rows
    
    for num_cubicles in range(1, 11): # Try up to 10 cubicles
        # Find widest row to filter candidate enclosures
        required_min_w = max((r["width"] for r in breaker_rows), default=0) + 100
        required_min_d = max((r["depth"] for r in breaker_rows), default=0) + 50
        
        candidates = [
            enclosure for enclosure in TRANOS_ENCLOSURES
            if get_record_value(enclosure, "width") >= required_min_w
            and get_record_value(enclosure, "depth") >= required_min_d
        ]
        candidates.sort(key=lambda item: get_record_value(item, "height")) # Start with shortest valid enclosure

        for enclosure in candidates:
            usable_height = get_record_value(enclosure, "height") - (
                BOTTOM_CLEARANCE + TOP_CLEARANCE + DISTRIBUTION_ROW_HEIGHT
            )
            if usable_height < 0:
                continue

            min_lower_height = 0
            if incoming_rows:
                min_lower_height = max(row["cp_height"] for row in incoming_rows)

            for lower_section_height in range(int(min_lower_height), int(usable_height + 1), 100):
                incoming_plan = pack_rows(
                    incoming_rows,
                    num_cubicles,
                    lower_section_height,
                    preferred_incoming_cubicles,
                )
                if incoming_plan is None:
                    continue

                upper_section_height = usable_height - lower_section_height
                outgoing_plan = pack_rows(
                    outgoing_rows,
                    num_cubicles,
                    upper_section_height,
                    preferred_outgoing_cubicles,
                )
                if outgoing_plan is None:
                    continue

                return {
                    "status": "Success",
                    "cubicles": num_cubicles,
                    "enclosure_used": enclosure,
                    "layout": {
                        "lower_rows": incoming_plan,
                        "upper_rows": outgoing_plan,
                        "distribution_row": distribution_row,
                        "lower_section_height": lower_section_height,
                        "upper_section_height": upper_section_height,
                    }
                }

    return {"status": "No Fit Found"}



def draw_cubicle_layout(packing_plan, enclosure_details):
    fig = go.Figure()
    
    # Extract enclosure dimensions for drawing the outer shells
    enc_w = get_record_value(enclosure_details, "width", 800)
    enc_h = get_record_value(enclosure_details, "height", 2000)
    lower_section_height = packing_plan.get("lower_section_height", 0)
    distribution_row = packing_plan.get("distribution_row", make_service_row(DISTRIBUTION_ROW_HEIGHT, "distribution", "distribution", "Distribution Space"))
    distribution_y0 = BOTTOM_CLEARANCE + lower_section_height
    distribution_y1 = distribution_y0 + distribution_row["cp_height"]
    upper_start_y = enc_h - TOP_CLEARANCE

    def row_style(row):
        row_type = row.get("row_type", "breaker")
        if row_type == "distribution":
            return dict(line_color="DarkGoldenRod", fill_color="rgba(255, 236, 179, 0.7)")
        if row_type == "terminal_blocks":
            return dict(line_color="SeaGreen", fill_color="rgba(204, 255, 204, 0.7)")
        if row_type == "cable_termination":
            return dict(line_color="SandyBrown", fill_color="rgba(255, 228, 196, 0.7)")
        return dict(line_color="Gray", fill_color="rgba(240, 240, 240, 0.7)")

    def draw_row(row, x_offset, row_y0, row_y1):
        cp_w = enc_w - 40
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
                x=x_offset + enc_w / 2,
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
    
    # Total spacing between cubicles (e.g., 50mm gap for visual clarity)
    gutter = 100 
    
    for cubicle_idx, lower_rows in enumerate(packing_plan.get("lower_rows", [])):
        # Calculate horizontal starting position for this cubicle
        x_offset = cubicle_idx * (enc_w + gutter)
        
        # 1. Draw the Main Enclosure Frame for this cubicle
        fig.add_shape(
            type="rect",
            x0=x_offset, y0=0, x1=x_offset + enc_w, y1=enc_h,
            line=dict(color="Black", width=3),
            fillcolor="rgba(200, 200, 200, 0.1)" # Faint gray background
        )
        
        # Add a label for the cubicle
        fig.add_annotation(
            x=x_offset + enc_w/2, y=enc_h + 50,
            text=f"Cubicle {cubicle_idx + 1}",
            showarrow=False, font=dict(size=14, weight="bold")
        )

        current_lower_y = BOTTOM_CLEARANCE
        for row in lower_rows:
            row_y0 = current_lower_y
            row_y1 = current_lower_y + row["cp_height"]
            draw_row(row, x_offset, row_y0, row_y1)
            current_lower_y += row["cp_height"]

        draw_row(distribution_row, x_offset, distribution_y0, distribution_y1)

        current_upper_y = upper_start_y
        for row in packing_plan.get("upper_rows", [[] for _ in packing_plan.get("lower_rows", [])])[cubicle_idx]:
            row_y1 = current_upper_y
            row_y0 = current_upper_y - row["cp_height"]
            draw_row(row, x_offset, row_y0, row_y1)
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
            Estimated_Enclosure = calculate_enclosure(
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
