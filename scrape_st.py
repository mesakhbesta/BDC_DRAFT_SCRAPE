import streamlit as st
import pandas as pd
import re, time, io
from datetime import datetime, date, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options

# === Setup Selenium (Firefox) ===
def create_driver():
    opts = Options()
    opts.add_argument("--headless")  # uncomment jika mau headless
    driver = webdriver.Firefox(options=opts)
    return driver

# === Utilities ===
def compute_days_ago_from_raw(raw_text):
    if not raw_text:
        return None
    txt = raw_text.strip().lower()
    # 'x days ago'
    m = re.match(r"(\d+)\s+days?\s+ago", txt)
    if m:
        return int(m.group(1))
    # 'x hours ago'
    m = re.match(r"(\d+)\s+hours?\s+ago", txt)
    if m:
        return 0
    if "yesterday" in txt:
        return 1
    if "today" in txt:
        return 0
    # Try parse absolute dates
    for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(txt, fmt).date()
            return (date.today() - dt).days
        except:
            pass
    return None

def duration_to_seconds(duration_str):
    if not duration_str:
        return None
    parts = duration_str.strip().split(":")
    try:
        parts = [int(p) for p in parts]
    except:
        return None
    if len(parts) == 2:
        return parts[0]*60 + parts[1]
    if len(parts) == 3:
        return parts[0]*3600 + parts[1]*60 + parts[2]
    return None

# === Scraper Function ===
def scrape_instagram_reel(url):
    match = re.search(r"/reel/([^/?]+)", url)
    if not match:
        return None
    video_id = match.group(1)
    driver = create_driver()
    target_url = f"https://social-tracker.com/stats/instagram/reels/{video_id}"
    driver.get(target_url)
    
    # === TUNGGU 15 DETIK supaya metrik penuh muncul ===
    time.sleep(15)
    
    data = {"url": url}
    
    try:
        # Fullname
        fullname = None
        try:
            h3_elems = driver.find_elements(By.CSS_SELECTOR, "h3.font-semibold.text-lg")
            for h in h3_elems:
                txt = h.text.strip()
                if txt and txt.lower() != "analytics":
                    fullname = txt
                    break
        except:
            fullname = None
        data["fullname"] = fullname

        # Username
        username = None
        try:
            rel_elem = driver.find_element(By.CSS_SELECTOR, "div > h3.font-semibold.text-lg + p.text-gray-500.text-sm")
            txt_rel = rel_elem.text.strip()
            if txt_rel.startswith("@"):
                username = txt_rel
            else:
                username = None
        except:
            elems = driver.find_elements(By.CSS_SELECTOR, "p.text-gray-500.text-sm")
            username = None
            for e in elems:
                t = e.text.strip()
                if t.startswith("@"):
                    username = t
                    break
        data["username"] = username

        # Upload date raw + days ago
        try:
            date_elem = driver.find_element(By.CSS_SELECTOR, "div.flex.items-center.space-x-2.text-gray-500 span.text-sm")
            raw_date = date_elem.text.strip()
            data["upload_date_raw"] = raw_date
            data["upload_days_ago"] = compute_days_ago_from_raw(raw_date)
        except:
            data["upload_date_raw"] = None
            data["upload_days_ago"] = None

        # Duration
        try:
            dur_elem = driver.find_element(By.CSS_SELECTOR, "div.absolute.bottom-2.right-2.bg-black.bg-opacity-70.text-white.px-2.py-1.rounded.text-sm")
            dur = dur_elem.text.strip()
            data["duration"] = dur
            data["duration_seconds"] = duration_to_seconds(dur)
        except:
            data["duration"] = None
            data["duration_seconds"] = None

        # Caption
        try:
            cap_elem = driver.find_element(By.CSS_SELECTOR, "p.text-gray-800.dark\\:text-gray-200.leading-relaxed")
            data["caption"] = cap_elem.text.strip()
        except:
            data["caption"] = None

        # Main stats
        try:
            elems_p = driver.find_elements(By.CSS_SELECTOR, "p.mt-2.text-2xl.font-bold")
            vals = [e.text.strip() for e in elems_p if e.text.strip()]
            if len(vals) >= 4:
                data["plays"], data["views"], data["likes"], data["comments"] = vals[:4]
        except:
            data.setdefault("plays", None)
            data.setdefault("views", None)
            data.setdefault("likes", None)
            data.setdefault("comments", None)

        # Additional stats
        try:
            elems_span = driver.find_elements(By.CSS_SELECTOR, "span.text-lg.font-bold")
            vals = [e.text.strip() for e in elems_span if e.text.strip()]
            if len(vals) >= 4:
                data["engagement"], data["like_rate"], data["comment_rate"], data["Play/View_Ratio"] = vals[:4]
        except:
            data.setdefault("engagement", None)
            data.setdefault("like_rate", None)
            data.setdefault("comment_rate", None)
            data.setdefault("Play/View_Ratio", None)

    except Exception as e:
        st.error(f"Error saat ambil elemen: {e}")

    driver.quit()
    return data

# === Streamlit UI ===
st.title("Instagram Reels Scraper 📊 (Social Tracker)")

input_type = st.radio("Pilih jenis input:", ["Link tunggal", "Upload file (Excel/CSV)"])
results = []

columns_order = [
    "url", "fullname", "username", "upload_date_raw", "upload_days_ago",
    "duration", "duration_seconds", "plays", "views", "likes", "comments",
    "engagement", "like_rate", "comment_rate", "Play/View_Ratio", "caption"
]

if input_type == "Link tunggal":
    url = st.text_input("Masukkan link Instagram Reel:")
    if st.button("Scrape Data"):
        if url:
            with st.spinner("⏳ Sedang scraping..."):
                data = scrape_instagram_reel(url)
            if data:
                results.append(data)
                df = pd.DataFrame(results)
                for c in columns_order:
                    if c not in df.columns:
                        df[c] = None
                df = df[columns_order]
                st.dataframe(df)
                
                buffer = io.BytesIO()
                df.to_excel(buffer, index=False, engine="openpyxl")
                buffer.seek(0)
                st.download_button(
                    label="Download Excel",
                    data=buffer,
                    file_name="result.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

elif input_type == "Upload file (Excel/CSV)":
    uploaded = st.file_uploader("Upload file:", type=["xlsx", "csv"])
    if uploaded:
        if uploaded.name.endswith(".csv"):
            df_in = pd.read_csv(uploaded)
        else:
            df_in = pd.read_excel(uploaded)

        st.write("Preview data:")
        st.dataframe(df_in.head())

        col_name = st.selectbox("Pilih kolom yang berisi link video:", df_in.columns)

        if st.button("Scrape Semua Data"):
            urls = df_in[col_name].dropna().tolist()
            progress = st.progress(0)
            status_text = st.empty()

            for i, url in enumerate(urls, start=1):
                status_text.text(f"⏳ Scraping {i}/{len(urls)} ...")
                data = scrape_instagram_reel(str(url))
                if data:
                    results.append(data)
                progress.progress(i / len(urls))

            status_text.text("✅ Semua link sudah diproses.")

            if results:
                df = pd.DataFrame(results)
                for c in columns_order:
                    if c not in df.columns:
                        df[c] = None
                df = df[columns_order]
                st.success("Scraping selesai ✅")
                st.dataframe(df)

                buffer = io.BytesIO()
                df.to_excel(buffer, index=False, engine="openpyxl")
                buffer.seek(0)
                st.download_button(
                    label="Download Excel",
                    data=buffer,
                    file_name="result.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
