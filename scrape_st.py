import streamlit as st
import pandas as pd
import re, time, io
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from yt_dlp import YoutubeDL

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

# === Ambil metadata via yt_dlp ===
def get_video_metadata(url):
    ydl_opts = {"quiet": True, "skip_download": True}
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        "title": info.get("title"),
        "uploader": info.get("uploader"),
        "duration": info.get("duration"),
        "description": info.get("description"),
    }

# === Scraper Function (metadata + stats) ===
def scrape_instagram_reel(url):
    # 1. ambil ID dari link
    match = re.search(r"/reel/([^/?]+)", url)
    if match:
        video_id = match.group(1)
    else:
        return None

    # 2. ambil metadata dulu (yt_dlp)
    meta = get_video_metadata(url)

    # 3. baru scraping stats (selenium)
    driver = get_driver()
    target_url = f"https://social-tracker.com/stats/instagram/reels/{video_id}"
    driver.get(target_url)
    time.sleep(20)  # tunggu load

    stats = {}
    try:
        elems_p = driver.find_elements(By.CSS_SELECTOR, "p.mt-2.text-2xl.font-bold")
        values_p = [e.text.strip() for e in elems_p if e.text.strip()]

        if len(values_p) >= 4:
            stats.update({
                "plays": values_p[0],
                "views": values_p[1],
                "likes": values_p[2],
                "comments": values_p[3]
            })

        elems_span = driver.find_elements(By.CSS_SELECTOR, "span.text-lg.font-bold")
        values_span = [e.text.strip() for e in elems_span if e.text.strip()]

        if len(values_span) >= 4:
            stats.update({
                "engagement": values_span[0],
                "like_rate": values_span[1],
                "comment_rate": values_span[2],
                "Play/View_Ratio": values_span[3]
            })

    except Exception as e:
        st.error(f"Error saat ambil elemen: {e}")

    driver.quit()

    # 4. gabungkan sesuai urutan: url → metadata → stats
    data = {"url": url}
    data.update(meta)
    data.update(stats)

    return data


# === Streamlit UI ===
st.title("Instagram Reels Scraper 📊")

input_type = st.radio("Pilih jenis input:", ["Link tunggal", "Upload file (Excel/CSV)"])

results = []

# === Mode Link Tunggal ===
if input_type == "Link tunggal":
    url = st.text_input("Masukkan link Instagram Reel:")
    if st.button("Scrape Data"):
        if url:
            with st.spinner("⏳ Sedang scrape data... tunggu sebentar"):
                data = scrape_instagram_reel(url)
            if data:
                results.append(data)
                df = pd.DataFrame(results)
                st.success("✅ Scraping selesai!")
                st.dataframe(df)

                # Simpan ke buffer
                buffer = io.BytesIO()
                df.to_excel(buffer, index=False, engine="openpyxl")
                buffer.seek(0)

                st.download_button(
                    label="Download Excel",
                    data=buffer,
                    file_name="result.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

# === Mode Upload File ===
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
                st.success("Scraping selesai semua link!")
                st.dataframe(df)

                # Simpan ke buffer
                buffer = io.BytesIO()
                df.to_excel(buffer, index=False, engine="openpyxl")
                buffer.seek(0)

                st.download_button(
                    label="Download Excel",
                    data=buffer,
                    file_name="result.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
