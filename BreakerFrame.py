import sqlite3
import streamlit as st
import dotenv
import os

from supabase import create_client, Client

dotenv.load_dotenv()

URL = os.getenv("SUPABASE_URL") or ""
KEY = os.getenv("SUPABASE_KEY") or ""

# Initialize the client
supabase: Client = create_client(URL, KEY)


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




def save_breaker(obj):
    data = {
        "class": type(obj).__name__,
        "model": obj.model,
        "type": obj.type,
        "pole": obj.pole,
        "min_current": obj.Min_current,
        "max_current": obj.Max_current,
        "height": obj.height,
        "width": obj.width,
        "depth": obj.depth
    }

    response = supabase.table("breaker_instances").insert(data).execute()
    return response
    


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
