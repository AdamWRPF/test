import pandas as pd
import streamlit as st
from pathlib import Path
from datetime import datetime

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------
CSV_PATH = Path(__file__).with_name("Records Master Sheet.csv")
LOGO_PATH = Path(__file__).with_name("wrpf_logo.png")

LIFT_MAP = {"S": "Squat", "B": "Bench", "D": "Deadlift", "T": "Total", "Total": "Total"}
LIFT_ORDER = ["Squat", "Bench", "Deadlift", "Total"]
INVALID_WEIGHT_CLASSES = {"736", "737", "738", "739", "cell"}

DIVISION_ORDER = [
    "T14-15", "T16-17", "T18-19", "Junior", "Opens",
    "M40-49", "M50-59", "M60-69", "M70-79",
]

# ------------------------------------------------------------------
# Load data
# ------------------------------------------------------------------
@st.cache_data
def load_data(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip()
    df = df[df["Full Name"].notna() & df["Weight"].notna()]
    df["Weight"] = pd.to_numeric(df["Weight"], errors="coerce")
    df["Class"] = df["Class"].astype(str).str.strip()
    df = df[~df["Class"].isin(INVALID_WEIGHT_CLASSES)]
    df["Division_raw"] = df["Division"].str.strip()
    df["Division_base"] = df["Division_raw"].str.replace(r"DT$", "", regex=True)
    df["Testing"] = df["Division_raw"].str.endswith("DT").map({True: "Drug Tested", False: "Untested"})
    df["Lift"] = df["Lift"].replace(LIFT_MAP).fillna(df["Lift"])
    df["Date_parsed"] = pd.to_datetime(df["Date"], errors="coerce")
    df.fillna("", inplace=True)
    return df

# ------------------------------------------------------------------
# Filter UI + Smart Search
# ------------------------------------------------------------------
def render_filters(df: pd.DataFrame):
    divs = list(dict.fromkeys(df["Division_base"].unique()))
    ordered_divs = [d for d in DIVISION_ORDER if d in divs] + [d for d in divs if d not in DIVISION_ORDER]
    weight_opts = sorted(df["Class"].unique(), key=lambda x: (pd.to_numeric(x, errors="coerce"), x))
    equipment_options = sorted(df["Equipment"].dropna().unique())
    equipment_display = ["Equipped" if e == "Multi-ply" else "Raw" if e == "Bare" else e for e in equipment_options]
    equipment_map = dict(zip(equipment_display, equipment_options))

    default_state = {
        "sex": "All", "division": "All", "testing_status": "All",
        "equipment": "All", "weight_class": "All", "search": ""
    }

    if "filters" not in st.session_state:
        st.session_state.filters = default_state.copy()

    with st.expander("Filters", expanded=True):
        cols = st.columns(6)
        sel = st.session_state.filters

        sel["sex"] = cols[0].selectbox("Sex", ["All"] + sorted(df["Sex"].dropna().unique()), index=0)
        sel["division"] = cols[1].selectbox("Division", ["All"] + ordered_divs, index=0)
        sel["testing_status"] = cols[2].selectbox("Testing", ["All", "Drug Tested", "Untested"], index=0)
        sel["equipment"] = cols[3].selectbox("Equipment", ["All"] + equipment_display, index=0)
        sel["weight_class"] = cols[4].selectbox("Weight", ["All"] + weight_opts, index=0)
        sel["search"] = cols[5].text_input("Search e.g. '110 junior Manchester'", value=sel["search"])

        if st.button("🔄 Reset Filters"):
            st.session_state.filters = default_state.copy()
            st.rerun()

    if sel["search"]:
        terms = sel["search"].lower().split()
        filtered = df.copy()
        for term in terms:
            filtered = filtered[
                filtered["Full Name"].str.lower().str.contains(term, na=False)
                | filtered["Record Name"].str.lower().str.contains(term, na=False)
                | filtered["Class"].str.lower().str.contains(term, na=False)
                | filtered["Division_base"].str.lower().str.contains(term, na=False)
                | filtered["Equipment"].str.lower().str.contains(term, na=False)
                | filtered["Testing"].str.lower().str.contains(term, na=False)
                | filtered["Location"].str.lower().str.contains(term, na=False)
            ]
        st.info("🔍 Search query detected — all filters ignored.")
        return filtered, sel

    filtered = df.copy()
    if sel["sex"] != "All":
        filtered = filtered[filtered["Sex"] == sel["sex"]]
    if sel["division"] != "All":
        filtered = filtered[filtered["Division_base"] == sel["division"]]
    if sel["testing_status"] != "All":
        filtered = filtered[filtered["Testing"] == sel["testing_status"]]
    if sel["equipment"] != "All":
        filtered = filtered[filtered["Equipment"] == equipment_map[sel["equipment"]]]
    if sel["weight_class"] != "All":
        filtered = filtered[filtered["Class"] == sel["weight_class"]]

    return filtered, sel

# ------------------------------------------------------------------
# Best records by class/lift
# ------------------------------------------------------------------
def best_per_class_and_lift(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.sort_values("Weight", ascending=False)
          .drop_duplicates(subset=["Class", "Lift"])
          .assign(
              _class_num=lambda d: pd.to_numeric(d["Class"], errors="coerce"),
              _lift_order=lambda d: d["Lift"].apply(lambda x: LIFT_ORDER.index(x) if x in LIFT_ORDER else 99)
          )
          .sort_values(["_class_num", "Class", "_lift_order"])
          .drop(columns=["_class_num", "_lift_order"])
    )

# ------------------------------------------------------------------
# Table Renderer
# ------------------------------------------------------------------
def render_table(filtered, sel, key=""):
    show_all = bool(sel["search"])
    data_source = filtered
    table_data = data_source if show_all else best_per_class_and_lift(data_source)

    st.subheader(
        f"{'All Matches' if show_all else 'Top Records'} – "
        f"{sel['division'] if sel['division'] != 'All' else 'All Divisions'} – "
        f"{sel['weight_class'] if sel['weight_class'] != 'All' else 'All Weight Classes'} – "
        f"{sel['testing_status']} – {sel['equipment'] if sel['equipment'] != 'All' else 'All Equipment'}"
    )

    display_df = table_data[[
        "Class", "Lift", "Weight", "Full Name", "Sex", "Division_base", "Testing",
        "Equipment", "Record Type", "Date", "Location"
    ]].copy()

    display_df = display_df.rename(columns={
        "Full Name": "Name", "Sex": "Gender", "Division_base": "Division",
        "Record Type": "Lift Type", "Location": "Event"
    })

    display_df["Lift Type"] = display_df["Lift Type"].apply(
        lambda x: "Single Lift" if "single" in x.lower() or "bench only" in x.lower() or "deadlift only" in x.lower() else "Full Power"
    )
    display_df["Weight"] = display_df["Weight"].apply(
        lambda x: int(x) if pd.notna(x) and float(x).is_integer() else x
    )

    display_df["Equipment"] = display_df["Equipment"].replace({
        "Multi-ply": "Equipped",
        "Bare": "Raw"
    })

    st.download_button(
        "📥 Download CSV",
        data=display_df.to_csv(index=False),
        file_name="filtered_records.csv",
        key=f"download_{key}"
    )

    st.markdown("""
        <style>
        .records-table {
            font-size: 14px;
            border-collapse: collapse;
            width: 100%;
            table-layout: auto;
            color: #000;
        }
        .records-table th, .records-table td {
            border: 1px solid #ddd;
            padding: 6px;
            word-wrap: break-word;
        }
        .records-table th {
            background-color: #cf1b2b;
            color: white;
            text-align: left;
            position: sticky;
            top: 0;
            z-index: 2;
        }
        .records-table tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        .records-table tr:nth-child(odd) {
            background-color: #ffffff;
        }
        .records-table td:nth-child(4) {
            white-space: normal;
            max-width: none;
            overflow: visible;
            text-overflow: unset;
        }
        </style>
    """, unsafe_allow_html=True)

    html_table = display_df.to_html(index=False, border=0, classes="records-table")
    st.markdown(html_table, unsafe_allow_html=True)

# ------------------------------------------------------------------
# Main App
# ------------------------------------------------------------------
def main():
    st.set_page_config("WRPF UK Records", layout="wide")

    nav_cols = st.columns(4)
    nav_links = {
        "Memberships": "https://www.wrpf.uk/memberships",
        "Results":     "https://www.wrpf.uk/results",
        "Events":      "https://www.wrpf.uk/events",
        "Livestreams": "https://www.wrpf.uk/live"
    }
    for (label, url), col in zip(nav_links.items(), nav_cols):
        col.markdown(f"<a href='{url}' target='_blank'><button style='width:100%'>{label}</button></a>", unsafe_allow_html=True)

    st.markdown("## **WRPF UK Records Database**")
    st.caption("Where Strength Meets Opportunity")

    df = load_data(CSV_PATH)
    filtered, sel = render_filters(df)

    tabs = st.tabs(["All Records", "Full Power", "Single Lifts", "By Location", "FAQ"])

    with tabs[0]:
        render_table(filtered, sel, key="all")

    with tabs[1]:
        full_power = filtered[~filtered["Record Type"].str.contains("Single", case=False, na=False)]
        render_table(full_power, sel, key="full")

    with tabs[2]:
        mask = filtered["Record Type"].str.contains("Single|Bench Only|Deadlift Only", case=False, na=False)
        single_lifts = filtered[mask & filtered["Lift"].isin(["Bench", "Deadlift"])]
        render_table(single_lifts, sel, key="single")

    with tabs[3]:
        st.markdown("## 📍 Records by Location")
        location_counts = (
            filtered[filtered["Location"].str.strip() != ""]
            .groupby("Location")
            .size()
            .reset_index(name="Number of Records")
            .sort_values("Number of Records", ascending=False)
        )
        st.dataframe(location_counts, use_container_width=True)

    with tabs[4]:
        st.markdown("## ❓ Frequently Asked Questions")
        st.markdown("""
**Q: How often is this database updated?**  
A: We update the records shortly after each WRPF UK sanctioned event.

**Q: What does 'Drug Tested' mean?**  
A: It refers to divisions where athletes are subject to in-competition testing.

**Q: What is the difference between Raw, Sleeves, Wraps and Equipped?**  
A: Raw is single lifts only and means no supportive equipment other than a belt and wrist wraps were worn.  
Sleeves is the division you fall under when wearing knee sleeves in a full power event.  
Wraps are the same but you're wearing knee wraps and Equipped is when you're wearing fully supportive suits.

**Q: How can I get a record updated or corrected?**  
A: Please contact [events@wrpf.uk](mailto:events@wrpf.uk) with evidence or questions.

**Q: What does Standard mean?**  
A: This is just a record standard selected from thousands of OpenPowerlifting entries.  
To claim it, break it by at least 0.5kg at any WRPF UK event.
        """)

if __name__ == "__main__":
    main()
