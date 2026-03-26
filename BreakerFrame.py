import sqlite3
import streamlit as st

Frame_Registry = {}

class RegistryMeta(type):
    def __init__(cls, name, bases, nmspc):
        super().__init__(name, bases, nmspc)
        # Skip registering the base class itself
        if name != "componentFrame":
            Frame_Registry[name.lower()] = cls

class componentFrame(metaclass=RegistryMeta):
    """Base class to handle shared logic."""
    def __init__(self, model, type, pole: int, Min_current: float, Max_current: float, Height:float, width:float, depth:float):
        self.model = model + " " + str(pole)
        self.type = type
        self.pole = pole
        self.Min_current = Min_current
        self.Max_current = Max_current
        self.height = Height
        self.width = width
        self.depth = depth
    def __repr__(self):
        # type(self).__name__ dynamically gets "Car" or "Bike"
        return f"{type(self).__name__}(model={self.model!r})"

class ACB(componentFrame):
    type = "acb"
    pass  # Inherits everything from componentFrame

class MCCB(componentFrame):
    type = "mccb"
    pass  # Inherits everything from componentFrame

class MCB(componentFrame):
    type = "mcb"
    pass  # Inherits everything from componentFrame

class RCBO(componentFrame):
    type = "rcbo"
    pass  # Inherits everything from componentFrame

class RCD(componentFrame):
    type = "rcd"
    pass  # Inherits everything from componentFrame

class DistributionBlock(componentFrame):
    type = "distribution_block"
    pass  # Inherits everything from componentFrame

# def save_registry(db_path="frame_registry.db"):
#     conn = sqlite3.connect(db_path)
#     cursor = conn.cursor()

#     cursor.execute("""
#     CREATE TABLE IF NOT EXISTS frame_registry (
#         key TEXT PRIMARY KEY,
#         class_name TEXT
#     )
#     """)

#     for k, v in Frame_Registry.items():
#         cursor.execute(
#             "INSERT INTO frame_registry (key, class_name) VALUES (?, ?)",
#             (k, v.__name__)
#         )

#     conn.commit()
#     conn.close()



def load_registry(db_path="frame_registry.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT key, class_name FROM frame_registry")
    rows = cursor.fetchall()

    conn.close()

    # Convert back to dictionary
    return {key: class_name for key, class_name in rows}


def save_breaker(obj, db_path="breaker_instances.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS breaker_instances (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class TEXT,
        model TEXT,
        type TEXT,
        pole INTEGER,
        min_current REAL,
        max_current REAL,
        height REAL,
        width REAL,
        depth REAL
    )
    """)

    cursor.execute(
        "INSERT INTO breaker_instances (class, model, type, pole, min_current, max_current, height, width, depth) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (type(obj).__name__, obj.model, obj.type, obj.pole, obj.Min_current, obj.Max_current, obj.height, obj.width, obj.depth)
    )

    conn.commit()
    conn.close()
    


def create_breaker(breaker_type: str, model: str, pole: int, Min_current: float, Max_current: float, Height: float, Width: float, Depth: float):
    """Create and save a breaker instance for a breaker type key.

    Returns the created object.
    """
    cls = Frame_Registry.get(breaker_type.strip().lower())
    if cls is None:
        raise ValueError(f"Unknown breaker type: {breaker_type}")

    obj = cls(model, cls.type, pole, Min_current, Max_current, Height, Width, Depth)
   
    save_breaker(obj)
    return obj


def main():
    st.title("Circuit Breaker Registry")
    choice = str(st.selectbox("Choose breaker", list(Frame_Registry.keys())))
    model = st.text_input("Model name")
    pole = st.number_input("Number of poles", min_value=1, max_value=4, step=1)
    Min_current = st.number_input("Minimum current", min_value=0.0)
    Max_current = st.number_input("Maximum current", min_value=0.0)
    Height = st.number_input("Height", min_value=1.0)
    Width = st.number_input("Width", min_value=1.0)
    Depth = st.number_input("Depth", min_value=1.0)
    if st.button("Create and Save"):
        if Height and Width and Depth is not None:
            try:
                create_breaker(choice, model, pole, Min_current, Max_current, Height, Width, Depth)
                st.success("Saved breaker instance to database")
            except Exception as e:
                st.error(f"Error: {e}")
        else:
            st.error("Please enter valid H, W, D values before saving.")



if __name__ == "__main__":
    main()
