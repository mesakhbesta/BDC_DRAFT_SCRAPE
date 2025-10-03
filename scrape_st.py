import streamlit as st
import pandas as pd
import re, time, io
from datetime import datetime, date, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

# === Setup Selenium (Headless Mode) ===
def get_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # headless mode
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--lang=en-US")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
    return driver

# === Utilities ===
def normalize_date_and_days(raw_text):
    """
    Return tuple (upload_date_raw, upload_days_ago)
    - upload_date_raw => always YYYY-MM-DD
    - upload_days_ago => always "X days ago"
    """
    if not raw_text:
        return None, None

    txt = raw_text.strip()
    low = txt.lower()
    today = date.today()

    # Case 1: "X days ago"
    m = re.match(r"^\s*(\d+)\s+days?\s+ago\s*$", low)
    if m:
        days = int(m.group(1))
        real_date = today - timedelta(days=days)
        return real_date.strftime("%Y-%m-%d"), f"{days} days ago"

    # Case 2: "yesterday"
    if "yesterday" in low:
        real_date = today - timedelta(days=1)
        return real_date.strftime("%Y-%m-%d"), "1 days ago"

    # Case 3: "today" or "X hours ago"
    if "today" in low or "hour" in low:
        return today.strftime("%Y-%m-%d"), "0 days ago"

    # Case 4: Absolute date (e.g. "9/26/2025")
    for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(txt, fmt).date()
            diff = (today - dt).days
            return dt.strftime("%Y-%m-%d"), f"{diff} days ago"
        except:
            pass

    # Fallback: just return raw text in first col
    return txt, None


def duration_to_seconds(duration_str):
    if not duration_str:
        return None
    s = duration_str.strip()
    parts = s.split(":")
    try:
        parts = [int(p) for p in parts]
    except:
        return None
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return None

# === Scraper Function (metadata + stats) ===
def scrape_instagram_reel(url):
    match = re.search(r"/reel/([^/?]+)", url)
    if not match:
        return None
    video_id = match.group(1)

    driver = get_driver()
    target_url = f"https://social-tracker.com/stats/instagram/reels/{video_id}"
    driver.get(target_url)
    time.sleep(10)  # adjust if needed

    data = {"url": url}

    try:
        # --- Fullname: pilih h3 pertama yang bukan "Analytics" ---
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

        # --- Username: robust extraction (prefer @handle) ---
        username = None
        try:
            rel_elem = driver.find_element(By.CSS_SELECTOR, "div > h3.font-semibold.text-lg + p.text-gray-500.text-sm")
            txt_rel = rel_elem.text.strip()
            if txt_rel and txt_rel.startswith("@"):
                username = txt_rel
            else:
                username = None
        except:
            username = None

        if not username:
            elems = driver.find_elements(By.CSS_SELECTOR, "p.text-gray-500.text-sm")
            picked = None
            for e in elems:
                t = e.text.strip()
                if t.startswith("@"):
                    picked = t
                    break
            if picked:
                username = picked
            else:
                if len(elems) >= 2:
                    username = elems[1].text.strip()
                elif len(elems) == 1:
                    username = elems[0].text.strip()
                else:
                    username = None
        data["username"] = username

        # --- Upload date raw + compute days ago ---
        try:
            date_elem = driver.find_element(
                By.CSS_SELECTOR, 
                "div.flex.items-center.space-x-2.text-gray-500 span.text-sm"
            )
            raw_date = date_elem.text.strip()
            norm_date, days_ago = normalize_date_and_days(raw_date)
            data["upload_date_raw"] = norm_date
            data["upload_days_ago"] = days_ago
        except:
            data["upload_date_raw"] = None
            data["upload_days_ago"] = None

        # --- Duration (string + seconds) ---
        try:
            duration_elem = driver.find_element(
                By.CSS_SELECTOR,
                "div.absolute.bottom-2.right-2.bg-black.bg-opacity-70.text-white.px-2.py-1.rounded.text-sm"
            )
            dur = duration_elem.text.strip()
            data["duration"] = dur
            data["duration_seconds"] = duration_to_seconds(dur)
        except:
            data["duration"] = None
            data["duration_seconds"] = None

        # --- Caption ---
        try:
            caption_elem = driver.find_element(By.CSS_SELECTOR, "p.text-gray-800.dark\\:text-gray-200.leading-relaxed")
            data["caption"] = caption_elem.text.strip()
        except:
            data["caption"] = None

        # --- Main stats (plays, views, likes, comments) ---
        try:
            elems_p = driver.find_elements(By.CSS_SELECTOR, "p.mt-2.text-2xl.font-bold")
            values_p = [e.text.strip() for e in elems_p if e.text.strip()]
            if len(values_p) >= 4:
                data["plays"] = values_p[0]
                data["views"] = values_p[1]
                data["likes"] = values_p[2]
                data["comments"] = values_p[3]
            else:
                data.setdefault("plays", None)
                data.setdefault("views", None)
                data.setdefault("likes", None)
                data.setdefault("comments", None)
        except:
            data.setdefault("plays", None)
            data.setdefault("views", None)
            data.setdefault("likes", None)
            data.setdefault("comments", None)

        # --- Additional stats (engagement, like_rate, comment_rate, play_view_ratio) ---
        try:
            elems_span = driver.find_elements(By.CSS_SELECTOR, "span.text-lg.font-bold")
            values_span = [e.text.strip() for e in elems_span if e.text.strip()]
            if len(values_span) >= 4:
                data["engagement"] = values_span[0]
                data["like_rate"] = values_span[1]
                data["comment_rate"] = values_span[2]
                data["Play/View_Ratio"] = values_span[3]
            else:
                data.setdefault("engagement", None)
                data.setdefault("like_rate", None)
                data.setdefault("comment_rate", None)
                data.setdefault("Play/View_Ratio", None)
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
    "url",
    "fullname",
    "username",
    "upload_date_raw",     # raw text as shown on web, e.g. "5 days ago" or "9/26/2025"
    "upload_days_ago",     # integer days difference (0 for today/within hours)
    "duration",
    "duration_seconds",
    "plays",
    "views",
    "likes",
    "comments",
    "engagement",
    "like_rate",
    "comment_rate",
    "Play/View_Ratio",
    "caption",
]

# Single link
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
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

# Bulk upload
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
                    mime="application/vnd.openxmlformats-officedocument-spreadsheetml.sheet",
                )
