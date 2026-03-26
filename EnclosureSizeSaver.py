import sqlite3
import streamlit as st

TranosEncase=[]
Height:int
Width:int
Depth:int

def saveEnclosureSize(EnclosureSize, db_path="enclosure_sizes.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS enclosure_sizes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        Height REAL,
        Width REAL,
        Depth REAL
    )
    """)

    cursor.execute(
        "INSERT INTO enclosure_sizes (Height, Width, Depth) VALUES (?, ?, ?)",
        (EnclosureSize[0], EnclosureSize[1], EnclosureSize[2])
    )

    conn.commit()
    conn.close()

def main():
    st.title("Enclosure Size Saver")
    st.write("Enter the dimensions of the enclosure:")

    Height = st.number_input("Height", min_value=1)
    Width = st.number_input("Width", min_value=1)
    Depth = st.number_input("Depth", min_value=1)

    if st.button("Save Enclosure Size"):
        if Height and Width and Depth is not None:
            EnclosureSize = [Height, Width, Depth]
            saveEnclosureSize(EnclosureSize)
            st.success("Enclosure size saved successfully!")
        else:
            st.error("Please enter valid H, W, D values before saving.")

if __name__ == "__main__":
    main()
       