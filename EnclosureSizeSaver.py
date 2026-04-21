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

TranosEncase=[]
Height:int
Width:int
Depth:int

def saveEnclosureSize(enclosure_size, Enclosure_type):
    data = {
        "height": enclosure_size[0],
        "width": enclosure_size[1],
        "depth": enclosure_size[2],
    }
    if Enclosure_type == "Free standing":
        return supabase.table("enclosure_sizes").insert(data).execute()
    else:
        return supabase.table("wallmounted_enclosure_sizes").insert(data).execute()

def main():
    st.title("Enclosure Size Saver")
    Enclosure_type = st.radio(
        "Select type of Enclosure",
        options=["Free standing", "Wall mounted"],
        horizontal=True,
    )
    st.write("Enter the dimensions of the enclosure:")
    Height = st.number_input("Height", min_value=1)
    Width = st.number_input("Width", min_value=1)
    Depth = st.number_input("Depth", min_value=1)

    if st.button("Save Enclosure Size"):
        if Height and Width and Depth is not None:
            EnclosureSize = [Height, Width, Depth]
            saveEnclosureSize(EnclosureSize, Enclosure_type)
            st.success("Enclosure size saved successfully!")
        else:
            st.error("Please enter valid H, W, D values before saving.")

if __name__ == "__main__":
    main()
       