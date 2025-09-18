import streamlit as st

from db import init_db
from pages.dogs import page_dogs
from pages.history import page_history
from pages.relationships import page_relationships
from pages.today import page_today

def main():
    st.set_page_config(page_title="Dog Playgroups", page_icon="🐶", layout="wide")
    init_db()
    page = st.sidebar.radio("Pages", ["Dogs", "Relationships", "Today", "History"])
    if page == "Dogs":
        page_dogs()
    elif page == "Relationships":
        page_relationships()
    elif page == "Today":
        page_today()
    else:
        page_history()

if __name__ == "__main__":
    main()
