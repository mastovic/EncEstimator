import math
import sqlite3
import streamlit as st
import plotly.graph_objects as go
from BreakerFrame import Frame_Registry, save_breaker

Component_Frames = []
TRANOS_ENCLOSURES = []



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


def get_cover_plate_height(breaker_height):
    if breaker_height <= 200: return 200
    if breaker_height <= 300: return 300
    return 400

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


def calculate_enclosure(incoming_list, outgoing_list):
    TRANOS_ENCLOSURES = load_Enclosure_registry()
    
    # 1. Determine the absolute maximum width available in your registry
    MAX_DB_WIDTH = max((e["width"] for e in TRANOS_ENCLOSURES), default=800) - 150 # -150 for margins
    
    incoming_rows = []
    outgoing_rows = []
    
    # 2. Process groups and split rows if they are too wide
    for group_name, group in [("incoming", incoming_list), ("outgoing", outgoing_list)]:
        height_map = {}
        for b in group:
            h = b["height"]
            height_map.setdefault(h, []).append(b)
        
        for h, breakers in height_map.items():
            current_row_breakers = []
            current_row_width = 0
            
            for b in breakers:
                breaker_width_with_gap = b["width"] + 5
                
                # If adding this breaker exceeds max width, close current row and start new one
                if current_row_width + breaker_width_with_gap > MAX_DB_WIDTH and current_row_breakers:
                    target_rows = incoming_rows if group_name == "incoming" else outgoing_rows
                    target_rows.append({
                        "cp_height": get_cover_plate_height(h),
                        "width": current_row_width,
                        "depth": max(br["depth"] for br in current_row_breakers),
                        "breakers": current_row_breakers,
                        "group": group_name
                    })
                    current_row_breakers = []
                    current_row_width = 0
                
                current_row_breakers.append(b)
                current_row_width += breaker_width_with_gap

            # Add the final/remaining breakers of this height group
            if current_row_breakers:
                target_rows = incoming_rows if group_name == "incoming" else outgoing_rows
                target_rows.append({
                    "cp_height": get_cover_plate_height(h),
                    "width": current_row_width,
                    "depth": max(br["depth"] for br in current_row_breakers),
                    "breakers": current_row_breakers,
                    "group": group_name
                })

    # 3. Bin Packing (First Fit Decreasing)
    incoming_rows.sort(key=lambda x: x['cp_height'], reverse=True)
    outgoing_rows.sort(key=lambda x: x['cp_height'], reverse=True)
    all_processed_rows = incoming_rows + outgoing_rows

    def preferred_cubicles(row_group, num_cubicles):
        if num_cubicles == 1:
            return [0]

        extra_cubicles = list(range(2, num_cubicles))
        if row_group == "incoming":
            return [0] + extra_cubicles + [1]
        return [1, 0] + extra_cubicles
    
    for num_cubicles in range(1, 11): # Try up to 10 cubicles
        # Find widest row to filter candidate enclosures
        required_min_w = max((r['width'] for r in all_processed_rows), default=0) + 100
        required_min_d = max((r['depth'] for r in all_processed_rows), default=0) + 50
        
        candidates = [e for e in TRANOS_ENCLOSURES if e["width"] >= required_min_w and e["depth"] >= required_min_d]
        candidates.sort(key=lambda x: x['height']) # Start with shortest valid enclosure

        for enclosure in candidates:
            # Add a "Vertical Busbar" tax if multi-cubicle
            usable_height = enclosure["height"] - (200+150+200) # Space for allowance, top/bottom cabling & horizontal busbar
            
            bins = [usable_height] * num_cubicles
            packing_plan = [[] for _ in range(num_cubicles)]
            
            fits = True
            for row in all_processed_rows:
                placed = False
                for i in preferred_cubicles(row.get("group"), num_cubicles):
                    if bins[i] >= row['cp_height']:
                        bins[i] -= row['cp_height']
                        packing_plan[i].append(row)
                        placed = True
                        break
                if not placed:
                    fits = False
                    break
            
            if fits:
                return {
                    "status": "Success",
                    "cubicles": num_cubicles,
                    "enclosure_used": enclosure,
                    "layout": packing_plan
                }

    return {"status": "No Fit Found"}



def draw_cubicle_layout(packing_plan, enclosure_details):
    fig = go.Figure()
    
    # Extract enclosure dimensions for drawing the outer shells
    enc_w = enclosure_details.get("width", 800)
    enc_h = enclosure_details.get("height", 2000)
    usable_height = enc_h - (200 + 150 + 200)
    top_start_y = enc_h - 200 - 150
    
    # Total spacing between cubicles (e.g., 50mm gap for visual clarity)
    gutter = 100 
    
    for cubicle_idx, rows in enumerate(packing_plan):
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

        # 2. Draw the Rows within this cubicle
        # Cubicle 1 fills from the bottom; extra cubicles fill from the top.
        current_y = 200
        current_top_y = top_start_y
        
        for row in rows:
            row_h = row['cp_height']
            # We use the enclosure width for the cover plate width
            cp_w = enc_w - 40 # Padding for frame

            if cubicle_idx == 0:
                row_y0 = current_y
                row_y1 = current_y + row_h
                current_y += row_h
            else:
                row_y1 = current_top_y
                row_y0 = current_top_y - row_h
                current_top_y -= row_h
            
            # Draw the Cover Plate
            fig.add_shape(
                type="rect",
                x0=x_offset + 20, y0=row_y0, 
                x1=x_offset + 20 + cp_w, y1=row_y1,
                line=dict(color="Gray", width=1, dash="dash"),
                fillcolor="rgba(240, 240, 240, 0.7)"
            )
            
            # 3. Draw Breakers inside the row
            # Center them horizontally within the cover plate
            total_breakers_w = sum(br['width'] + 5 for br in row['breakers'])
            current_x = x_offset + 20 + (cp_w - total_breakers_w) / 2
            
            for br in row['breakers']:
                br_w = br['width']
                br_h = br['height']
                
                # Vertical centering within cover plate
                y_offset = (row_h - br_h) / 2
                
                # Draw the Breaker Box
                fig.add_shape(
                    type="rect",
                    x0=current_x, y0=row_y0 + y_offset, 
                    x1=current_x + br_w, y1=row_y0 + y_offset + br_h,
                    line=dict(color="RoyalBlue", width=2),
                    fillcolor="LightSkyBlue"
                )
                
                # Add Hover Info
                fig.add_trace(go.Scatter(
                    x=[current_x + br_w/2],
                    y=[row_y0 + row_h/2],
                    text=[f"<b>{br.get('model')}</b><br>W: {br_w}mm<br>H: {br_h}mm<br>D: {br.get('depth')}mm"],
                    mode="markers",
                    marker=dict(opacity=0),
                    hoverinfo="text",
                    showlegend=False
                ))
                
                current_x += (br_w + 5) # 5mm gap

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

def main():
    st.title("Enclosure Size Estimator")
   
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
            Estimated_Enclosure = calculate_enclosure(Selected_incoming, Selected_outgoing)
            Status = Estimated_Enclosure.get("status")
            Cubicle_Count = Estimated_Enclosure.get("cubicles")
            selected_enclosure = Estimated_Enclosure.get("enclosure_used")
            Panel_Layout = Estimated_Enclosure.get("layout")
            st.write(f"Calculation Status: {Status}")
            st.write(f"Recommended Tranos Enclosure: {selected_enclosure}")
            st.write(f"Number of Cubicles: {Cubicle_Count}")
            fig = draw_cubicle_layout(Panel_Layout, selected_enclosure)
            st.plotly_chart(fig, use_container_width=True)
    else:
            st.error("Could not find a valid enclosure for these components.")


if __name__ == "__main__":
    main()
