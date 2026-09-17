"""Streamlit dashboard for the Advanced Steganography System (v2).

New in this version:
    - A bilingual (English/Bangla) welcome screen.
    - A guided Hide / Detect wizard covering all 9 carrier x payload
      combinations (Image/Audio/Video carrier x Text/Audio/Video payload).
    - A "Detect Hidden Data" mode that inspects a suspicious file and reports
      what kind of payload (if any) is hidden inside it.
    - All previous advanced tools (Multi-Image Experiment, Saved Results)
      remain available from the sidebar for continuity.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from analysis.audio_metrics import full_audio_report
from analysis.binary_payload_metrics import full_image_payload_report, full_video_payload_report
from analysis.experiment import run_multi_image_experiment
from analysis.extended_audio_metrics import compare_extended_audio_metrics
from analysis.extended_image_metrics import compare_extended_image_metrics
from analysis.extended_video_metrics import compare_extended_video_metrics
from analysis.image_metrics import full_image_report, generate_difference_image
from analysis.text_metrics import full_text_report
from analysis.video_metrics import full_video_quality_report
from steganography import universal
from steganography.image_io import load_cover_image
from steganography.payload import ChecksumMismatchError, InvalidLengthError, InvalidMagicError, InvalidVersionError, PayloadError
from steganography.text_carrier import TextCarrierError
from steganography.video_carrier import VideoCarrierError, load_video_frames
from steganography.audio_carrier import AudioCarrierError
from steganography.lsb import LSBCapacityError
from utils.file_utils import ensure_dir, human_readable_size, save_csv, save_json
from utils.validators import ValidationError

UPLOADS_DIR = "uploads"
OUTPUTS_DIR = "outputs"
RESULTS_DIR = "results"

ensure_dir(UPLOADS_DIR)
ensure_dir(OUTPUTS_DIR)
ensure_dir(RESULTS_DIR)

st.set_page_config(page_title="Advanced Steganography System", layout="wide", page_icon="🔐")

CARRIER_LABELS = {
    "image": "🖼️ Image / ছবি",
    "audio": "🎵 Audio / অডিও",
    "video": "🎬 Video / ভিডিও",
    "text": "📄 Text file / টেক্সট ফাইল",
}
PAYLOAD_LABELS = {
    "text": "📝 Text / টেক্সট",
    "audio": "🎵 Audio / অডিও",
    "video": "🎬 Video / ভিডিও",
    "image": "🖼️ Image / ছবি",
}
CARRIER_EXTS = {
    "image": ["png", "jpg", "jpeg", "gif", "bmp"],
    "audio": ["wav"],
    "video": ["avi", "mp4", "mkv", "mov"],
    "text": ["txt"],
}
CARRIER_OUT_EXT = {"image": ".png", "audio": ".wav", "video": ".avi", "text": ".txt"}

COMBO_NUMBER = {
    (c, p): i + 1
    for i, (c, p) in enumerate(
        [(c, p) for c in ["image", "audio", "video", "text"] for p in ["text", "audio", "video", "image"]]
    )
}


def save_uploaded_file(uploaded_file, target_dir: str) -> str:
    ensure_dir(target_dir)
    path = os.path.join(target_dir, uploaded_file.name)
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return path


def reset_wizard():
    for key in list(st.session_state.keys()):
        if key.startswith("wiz_"):
            del st.session_state[key]
    st.session_state["wiz_stage"] = "welcome"


def embedding_settings_widget(key_prefix: str):
    col1, col2, col3 = st.columns(3)
    with col1:
        bit_depth = st.selectbox("LSB bit depth / বিট গভীরতা", [1, 2], key=f"{key_prefix}_bd")
    with col2:
        mode = st.selectbox("Embedding mode / এমবেডিং মোড", ["sequential", "random"], key=f"{key_prefix}_mode")
    seed = None
    with col3:
        if mode == "random":
            seed = st.number_input("Seed / key", min_value=0, value=42, step=1, key=f"{key_prefix}_seed")
    return bit_depth, mode, seed


def show_extended_metrics(carrier: str, cover_path: str, stego_path: str):
    """Compute and display both the classic (MSE/PSNR/SSIM) and extended
    (photo/audio/video-parameter-style) quality comparison between the cover
    and stego carrier file, if applicable."""
    try:
        if carrier == "image":
            cover_arr = load_cover_image(cover_path)
            stego_arr = load_cover_image(stego_path)

            classic = full_image_report(cover_arr, stego_arr)
            st.markdown("**Carrier quality summary / ছবির মিল-অমিলের সারসংক্ষেপ:**")
            psnr_str = "Infinity (perfect)" if classic["psnr_db"] == float("inf") else f"{classic['psnr_db']} dB"
            st.write(
                f"- **Pixel Similarity (unchanged pixels):** {classic['unchanged_percent']}%  "
                f"(**{classic['modified_percent']}%** of pixels were modified)\n"
                f"- **MSE:** {classic['mse']}\n"
                f"- **PSNR:** {psnr_str}\n"
                f"- **SSIM:** {classic['ssim']} (1.0 = perfect structural match)"
            )

            report = compare_extended_image_metrics(cover_arr, stego_arr)
            st.markdown("**Extended image quality parameters / বিস্তারিত ছবির মান পরিমাপ:**")
            df = pd.DataFrame(report).T.reset_index().rename(columns={"index": "parameter"})
            st.dataframe(df, use_container_width=True)

        elif carrier == "audio":
            cover_bytes = Path(cover_path).read_bytes()
            stego_bytes = Path(stego_path).read_bytes()

            classic = full_audio_report(cover_bytes, stego_bytes)
            st.markdown("**Carrier quality summary / অডিওর মিল-অমিলের সারসংক্ষেপ:**")
            st.write(
                f"- **Byte accuracy:** {classic['byte_accuracy_percent']}% "
                f"(exact match: {classic['exact_byte_match']})\n"
                + (
                    f"- **Signal correlation:** {classic['signal_level'].get('correlation')}  "
                    f"**SNR:** {classic['signal_level'].get('snr_db')} dB"
                    if classic["signal_level"].get("available")
                    else "- Signal-level comparison unavailable."
                )
            )

            report = compare_extended_audio_metrics(cover_bytes, stego_bytes)
            if report.get("available"):
                st.markdown("**Extended audio quality parameters / বিস্তারিত অডিওর মান পরিমাপ:**")
                rows = {k: v for k, v in report.items() if k != "available"}
                df = pd.DataFrame(rows).T.reset_index().rename(columns={"index": "parameter"})
                st.dataframe(df, use_container_width=True)
            else:
                st.caption(f"Extended audio metrics unavailable: {report.get('reason')}")

        elif carrier == "video":
            cover_frames, _, _, _ = load_video_frames(cover_path)
            stego_frames, _, _, _ = load_video_frames(stego_path)

            classic = full_video_quality_report(cover_frames, stego_frames, frame_stride=5)
            if classic.get("available"):
                st.markdown("**Carrier quality summary / ভিডিওর মিল-অমিলের সারসংক্ষেপ:**")
                psnr_str = "Infinity (perfect)" if classic["average_psnr_db"] == float("inf") else f"{classic['average_psnr_db']} dB"
                st.write(
                    f"- **Unchanged pixels (avg):** {classic['average_unchanged_pixel_percent']}%  "
                    f"(**{classic['average_modified_pixel_percent']}%** modified)\n"
                    f"- **Average MSE:** {classic['average_mse']}\n"
                    f"- **Average PSNR:** {psnr_str}\n"
                    f"- **Average SSIM:** {classic['average_ssim']}\n"
                    f"- **Frames analyzed:** {classic['frames_analyzed']} "
                    f"({classic['perfect_match_frames']} were pixel-perfect)"
                )

            report = compare_extended_video_metrics(cover_frames, stego_frames, frame_stride=5)
            if report.get("available"):
                st.markdown(f"**Extended video quality parameters / বিস্তারিত ভিডিওর মান পরিমাপ** (sampled {report.get('frames_analyzed')} frames):")
                rows = {k: v for k, v in report.items() if k not in ("available", "frames_analyzed")}
                df = pd.DataFrame(rows).T.reset_index().rename(columns={"index": "parameter"})
                st.dataframe(df, use_container_width=True)
            else:
                st.caption(f"Extended video metrics unavailable: {report.get('reason')}")
        # text carrier has no visual/audio quality parameters to compare
    except Exception as exc:  # extended metrics are a bonus display; never block the main flow
        st.caption(f"(Extended metrics could not be computed: {exc})")


# =====================================================================
# WELCOME / WIZARD FLOW
# =====================================================================

def page_wizard():
    st.session_state.setdefault("wiz_stage", "welcome")
    stage = st.session_state["wiz_stage"]

    if stage == "welcome":
        _stage_welcome()
    elif stage == "choose_carrier":
        _stage_choose_carrier()
    elif stage == "choose_payload":
        _stage_choose_payload()
    elif stage == "hide_work":
        _stage_hide_work()
    elif stage == "detect_choose_carrier":
        _stage_detect_choose_carrier()
    elif stage == "detect_work":
        _stage_detect_work()
    elif stage == "compare_choose_type":
        _stage_compare_choose_type()
    elif stage == "compare_work":
        _stage_compare_work()
    else:
        st.session_state["wiz_stage"] = "welcome"
        st.rerun()


def _stage_welcome():
    st.markdown(
        """
        <div style="text-align:center; padding: 2rem 0;">
        <h1>🔐 Advanced Steganography System</h1>
        <h3 style="color:#888; font-weight:normal;">উন্নত স্টেগানোগ্রাফি সিস্টেম</h3>
        <p style="font-size:1.1rem; max-width:700px; margin:1rem auto;">
        Hide secret text, audio, or video inside an image, audio, or video file —
        detect and reveal hidden data from a suspicious file — or directly compare
        any two files to see how similar they are.<br>
        গোপন টেক্সট, অডিও বা ভিডিও লুকান একটি ছবি, অডিও বা ভিডিও ফাইলের ভেতরে —
        সন্দেহজনক কোনো ফাইল থেকে লুকানো তথ্য খুঁজে বের করুন — অথবা সরাসরি যেকোনো দুটো ফাইল
        তুলনা করে দেখুন কতটা মিল আছে।
        </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("### 🔒 Hide Data / তথ্য লুকান")
        st.write("Hide a secret message, audio, or video file inside a cover file.")
        st.write("একটি কভার ফাইলের ভেতরে গোপন বার্তা, অডিও বা ভিডিও লুকান।")
        if st.button("Start Hiding / লুকানো শুরু করুন ➜", use_container_width=True, type="primary", key="wiz_start_hide"):
            st.session_state["wiz_stage"] = "choose_carrier"
            st.rerun()
    with col2:
        st.markdown("### 🔍 Detect Hidden Data / লুকানো তথ্য খুঁজুন")
        st.write("Check a file and reveal what secret data (if any) is hidden inside it.")
        st.write("কোনো ফাইল যাচাই করে দেখুন তার ভেতরে কী গোপন তথ্য (যদি থাকে) লুকানো আছে।")
        if st.button("Start Detecting / খোঁজা শুরু করুন ➜", use_container_width=True, type="primary", key="wiz_start_detect"):
            st.session_state["wiz_stage"] = "detect_choose_carrier"
            st.rerun()
    with col3:
        st.markdown("### 🆚 Compare Two Files / দুটো ফাইল তুলনা করুন")
        st.write("Directly compare any two images, audios, videos, or texts and see how much they match.")
        st.write("সরাসরি যেকোনো দুটো ছবি, অডিও, ভিডিও, বা টেক্সট তুলনা করে দেখুন কতটা মিলছে।")
        if st.button("Start Comparing / তুলনা শুরু করুন ➜", use_container_width=True, type="primary", key="wiz_start_compare"):
            st.session_state["wiz_stage"] = "compare_choose_type"
            st.rerun()

    st.divider()
    st.caption(
        "This system supports 16 combinations: Image/Audio/Video/Text as the carrier, "
        "each with Text/Audio/Video/Image as the hidden data. এই সিস্টেম ১৬টি সমন্বয় সমর্থন করে।"
    )


def _stage_compare_choose_type():
    st.subheader("What type of files do you want to compare? / কোন ধরনের ফাইল তুলনা করতে চান?")

    file_type_labels = {
        "image": "🖼️ Image / ছবি",
        "audio": "🎵 Audio / অডিও",
        "video": "🎬 Video / ভিডিও",
        "text": "📄 Text / টেক্সট",
    }
    cols = st.columns(len(file_type_labels))
    for col, (key, label) in zip(cols, file_type_labels.items()):
        with col:
            if st.button(label, use_container_width=True, key=f"wiz_compare_type_{key}"):
                st.session_state["wiz_compare_type"] = key
                st.session_state["wiz_stage"] = "compare_work"
                st.rerun()

    st.divider()
    if st.button("⬅ Back / পিছনে", key="wiz_compare_back_1"):
        st.session_state["wiz_stage"] = "welcome"
        st.rerun()


def _stage_compare_work():
    file_type = st.session_state["wiz_compare_type"]
    labels = {"image": "🖼️ Image", "audio": "🎵 Audio", "video": "🎬 Video", "text": "📄 Text"}
    st.subheader(f"🆚 Compare two {labels[file_type]} files")
    if st.button("⬅ Change file type / ফাইলের ধরন পরিবর্তন করুন", key="wiz_compare_back_2"):
        st.session_state["wiz_stage"] = "compare_choose_type"
        st.rerun()

    exts = CARRIER_EXTS[file_type]
    col1, col2 = st.columns(2)
    with col1:
        file_a = st.file_uploader("First file / প্রথম ফাইল (A)", type=exts, key="wiz_compare_file_a")
        if file_a is not None and file_type == "image":
            st.image(file_a, caption="File A")
    with col2:
        file_b = st.file_uploader("Second file / দ্বিতীয় ফাইল (B)", type=exts, key="wiz_compare_file_b")
        if file_b is not None and file_type == "image":
            st.image(file_b, caption="File B")

    if file_type == "text":
        st.caption(
            "Tip: for text, you can also paste directly instead of uploading .txt files. / "
            "চাইলে সরাসরি লিখেও তুলনা করতে পারেন, .txt ফাইল লাগবেই না।"
        )
        use_paste = st.checkbox("Paste text instead of uploading files / ফাইলের বদলে সরাসরি লিখুন", key="wiz_compare_paste")
        if use_paste:
            text_a = st.text_area("Text A", height=100, key="wiz_compare_text_a")
            text_b = st.text_area("Text B", height=100, key="wiz_compare_text_b")
            file_a = file_b = None
        else:
            text_a = text_b = None

    ready = (file_type == "text" and st.session_state.get("wiz_compare_paste") and text_a and text_b) or (
        file_a is not None and file_b is not None
    )

    if st.button("🆚 Compare / তুলনা করুন", type="primary", disabled=not ready, key="wiz_compare_btn"):
        try:
            if file_type == "image":
                path_a = save_uploaded_file(file_a, UPLOADS_DIR)
                path_b = save_uploaded_file(file_b, UPLOADS_DIR)
                arr_a = load_cover_image(path_a)
                arr_b = load_cover_image(path_b)

                classic = full_image_report(arr_a, arr_b)
                st.markdown("**Classic comparison / সাধারণ তুলনা:**")
                psnr_str = "Infinity (perfect)" if classic["psnr_db"] == float("inf") else f"{classic['psnr_db']} dB"
                st.write(
                    f"- **Pixel Similarity:** {classic['unchanged_percent']}%  "
                    f"(**{classic['modified_percent']}%** different)\n"
                    f"- **MSE:** {classic['mse']}\n"
                    f"- **PSNR:** {psnr_str}\n"
                    f"- **SSIM:** {classic['ssim']}"
                )
                if arr_a.shape == arr_b.shape:
                    diff = generate_difference_image(arr_a, arr_b)
                    st.image(diff, caption="Difference map (amplified)")

                report = compare_extended_image_metrics(arr_a, arr_b)
                st.markdown("**Extended parameters / বিস্তারিত পরিমাপ:**")
                df = pd.DataFrame(report).T.reset_index().rename(columns={"index": "parameter"})
                st.dataframe(df, use_container_width=True)

            elif file_type == "audio":
                bytes_a = file_a.getvalue()
                bytes_b = file_b.getvalue()

                classic = full_audio_report(bytes_a, bytes_b)
                st.markdown("**Classic comparison / সাধারণ তুলনা:**")
                st.write(f"- **Byte accuracy:** {classic['byte_accuracy_percent']}% (exact match: {classic['exact_byte_match']})")
                if classic["signal_level"].get("available"):
                    st.write(
                        f"- **Signal correlation:** {classic['signal_level'].get('correlation')}  "
                        f"**SNR:** {classic['signal_level'].get('snr_db')} dB"
                    )
                else:
                    st.caption(f"Signal-level comparison unavailable: {classic['signal_level'].get('reason')}")

                report = compare_extended_audio_metrics(bytes_a, bytes_b)
                if report.get("available"):
                    st.markdown("**Extended parameters / বিস্তারিত পরিমাপ:**")
                    rows = {k: v for k, v in report.items() if k != "available"}
                    df = pd.DataFrame(rows).T.reset_index().rename(columns={"index": "parameter"})
                    st.dataframe(df, use_container_width=True)
                else:
                    st.caption(f"Extended metrics unavailable: {report.get('reason')}")

            elif file_type == "video":
                path_a = save_uploaded_file(file_a, UPLOADS_DIR)
                path_b = save_uploaded_file(file_b, UPLOADS_DIR)
                frames_a, _, _, _ = load_video_frames(path_a)
                frames_b, _, _, _ = load_video_frames(path_b)

                classic = full_video_quality_report(frames_a, frames_b, frame_stride=5)
                if classic.get("available"):
                    st.markdown("**Classic comparison / সাধারণ তুলনা:**")
                    psnr_str = "Infinity (perfect)" if classic["average_psnr_db"] == float("inf") else f"{classic['average_psnr_db']} dB"
                    st.write(
                        f"- **Unchanged pixels (avg):** {classic['average_unchanged_pixel_percent']}%\n"
                        f"- **Average MSE:** {classic['average_mse']}\n"
                        f"- **Average PSNR:** {psnr_str}\n"
                        f"- **Average SSIM:** {classic['average_ssim']}\n"
                        f"- **Frames analyzed:** {classic['frames_analyzed']}"
                    )
                else:
                    st.warning(classic.get("reason"))

                report = compare_extended_video_metrics(frames_a, frames_b, frame_stride=5)
                if report.get("available"):
                    st.markdown("**Extended parameters / বিস্তারিত পরিমাপ:**")
                    rows = {k: v for k, v in report.items() if k not in ("available", "frames_analyzed")}
                    df = pd.DataFrame(rows).T.reset_index().rename(columns={"index": "parameter"})
                    st.dataframe(df, use_container_width=True)

            elif file_type == "text":
                if st.session_state.get("wiz_compare_paste"):
                    ta, tb = text_a, text_b
                else:
                    ta = file_a.getvalue().decode("utf-8")
                    tb = file_b.getvalue().decode("utf-8")
                st.markdown("**Comparison report / তুলনার রিপোর্ট:**")
                st.json(full_text_report(ta, tb))

        except Exception as exc:
            st.error(f"Could not compare these files: {exc}")


def _stage_choose_carrier():
    st.subheader("Step 1 / ধাপ ১: What do you want to hide something *inside*?")
    st.caption("আপনি *কীসের মধ্যে* কিছু লুকাতে চান?")

    cols = st.columns(len(CARRIER_LABELS))
    for col, (key, label) in zip(cols, CARRIER_LABELS.items()):
        with col:
            if st.button(label, use_container_width=True, key=f"wiz_carrier_{key}"):
                st.session_state["wiz_carrier"] = key
                st.session_state["wiz_stage"] = "choose_payload"
                st.rerun()

    st.divider()
    if st.button("⬅ Back / পিছনে", key="wiz_back_1"):
        st.session_state["wiz_stage"] = "welcome"
        st.rerun()


def _stage_choose_payload():
    carrier = st.session_state.get("wiz_carrier")
    st.subheader(f"Step 2 / ধাপ ২: What do you want to hide inside the {carrier}?")
    st.caption("আপনি কী লুকাতে চান?")

    payload_options = PAYLOAD_LABELS

    cols = st.columns(len(payload_options))
    for col, (key, label) in zip(cols, payload_options.items()):
        with col:
            if st.button(label, use_container_width=True, key=f"wiz_payload_{key}"):
                st.session_state["wiz_payload"] = key
                st.session_state["wiz_stage"] = "hide_work"
                st.rerun()

    st.divider()
    if st.button("⬅ Back / পিছনে", key="wiz_back_2"):
        st.session_state["wiz_stage"] = "choose_carrier"
        st.rerun()


def _stage_hide_work():
    carrier = st.session_state["wiz_carrier"]
    payload_kind = st.session_state["wiz_payload"]
    combo_num = COMBO_NUMBER[(carrier, payload_kind)]

    st.subheader(f"Combination #{combo_num} of 16: {CARRIER_LABELS[carrier]} + {PAYLOAD_LABELS[payload_kind]}")
    if st.button("⬅ Change selection / পরিবর্তন করুন", key="wiz_back_3"):
        st.session_state["wiz_stage"] = "choose_carrier"
        st.rerun()

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("#### 1. Encode / এনকোড করুন")
        cover_file = st.file_uploader(
            f"Cover {carrier} file", type=CARRIER_EXTS[carrier], key="wiz_cover_file"
        )

        text_val = None
        secret_bytes = None
        secret_filename = "secret"

        if payload_kind == "text":
            input_mode = st.radio("Secret text input", ["Type text", "Upload .txt file"], key="wiz_text_mode")
            if input_mode == "Type text":
                text_val = st.text_area("Secret message / গোপন বার্তা", height=100, key="wiz_text_area")
            else:
                txt_file = st.file_uploader("Secret .txt file", type=["txt"], key="wiz_text_file")
                if txt_file is not None:
                    text_val = txt_file.getvalue().decode("utf-8")
                    st.text_area("Preview", text_val, height=100, disabled=True)
        else:
            payload_exts = CARRIER_EXTS[payload_kind]
            secret_file = st.file_uploader(f"Secret {payload_kind} file", type=payload_exts, key="wiz_secret_file")
            if secret_file is not None:
                secret_path = save_uploaded_file(secret_file, UPLOADS_DIR)
                secret_bytes = Path(secret_path).read_bytes()
                secret_filename = secret_file.name

        bit_depth, mode, seed = embedding_settings_widget("wiz_enc")

        ready_to_encode = cover_file is not None and (
            (payload_kind == "text" and text_val is not None and text_val != "")
            or (payload_kind != "text" and secret_bytes is not None)
        )

        cover_path = None
        if cover_file is not None:
            cover_path = save_uploaded_file(cover_file, UPLOADS_DIR)
            try:
                capacity = universal.carrier_capacity(carrier, cover_path, bit_depth)
                payload_preview = universal.build_payload_for(
                    payload_kind, text=text_val or "", secret_bytes=secret_bytes or b"", secret_filename=secret_filename
                )
                st.caption(
                    f"Capacity: {human_readable_size(capacity)} | "
                    f"Payload: {human_readable_size(len(payload_preview))} "
                    f"({(len(payload_preview) / capacity * 100) if capacity else 0:.2f}% of capacity)"
                )
                if len(payload_preview) > capacity:
                    st.error("⚠ Insufficient capacity / অপর্যাপ্ত ধারণক্ষমতা: pick a larger cover file, lower payload, or a higher bit depth.")
            except (AudioCarrierError, VideoCarrierError, TextCarrierError) as exc:
                st.error(str(exc))
                cover_path = None

        if st.button("🔒 Encode / এনকোড করুন", type="primary", disabled=not ready_to_encode, key="wiz_encode_btn"):
            try:
                payload = universal.build_payload_for(
                    payload_kind, text=text_val, secret_bytes=secret_bytes, secret_filename=secret_filename
                )
                out_name = f"{Path(cover_path).stem}_stego{CARRIER_OUT_EXT[carrier]}"
                out_path = os.path.join(OUTPUTS_DIR, out_name)
                info = universal.encode(carrier, cover_path, payload, out_path, bit_depth=bit_depth, mode=mode, seed=seed)
                st.session_state["wiz_stego_path"] = out_path
                st.session_state["wiz_cover_path"] = cover_path
                st.session_state["wiz_carrier_used"] = carrier
                if payload_kind == "text":
                    st.session_state["wiz_original_text"] = text_val
                else:
                    st.session_state["wiz_original_bytes"] = secret_bytes
                st.success(f"✅ Encoding successful! / এনকোডিং সফল হয়েছে!")
                st.json(info)
                if carrier == "image":
                    st.image(out_path, caption="Stego image")
                elif carrier == "audio":
                    st.audio(out_path)
                elif carrier == "video":
                    st.video(out_path)
                with open(out_path, "rb") as f:
                    st.download_button("⬇ Download stego file", f, file_name=out_name, key="wiz_download_stego")

                if carrier in ("image", "audio", "video"):
                    with st.spinner("Computing extended quality comparison..."):
                        show_extended_metrics(carrier, cover_path, out_path)
            except ValidationError as exc:
                st.error(str(exc))
            except (LSBCapacityError, AudioCarrierError, VideoCarrierError, TextCarrierError) as exc:
                st.error(str(exc))

    with col_right:
        st.markdown("#### 2. Decode & Verify / ডিকোড ও যাচাই")
        dec_bit_depth, dec_mode, dec_seed = embedding_settings_widget("wiz_dec")

        source = st.radio("Stego file source", ["Use last encoded file", "Upload a stego file"], key="wiz_dec_source")
        stego_path_to_decode = None
        uploaded_original_bytes = None
        uploaded_original_text = None
        if source == "Use last encoded file" and "wiz_stego_path" in st.session_state:
            stego_path_to_decode = st.session_state["wiz_stego_path"]
            st.caption(f"Using: {stego_path_to_decode}")
        else:
            up = st.file_uploader(f"Stego {carrier} file", type=CARRIER_EXTS[carrier], key="wiz_stego_upload")
            if up is not None:
                stego_path_to_decode = save_uploaded_file(up, UPLOADS_DIR)

            st.caption(
                "Optional: also upload the original secret file to see the exact match "
                "percentage after extraction. / ঐচ্ছিক: নিষ্কাশনের পর কত শতাংশ মিলেছে দেখতে "
                "আসল গোপন ফাইলটাও আপলোড করুন।"
            )
            orig_up = st.file_uploader(
                "Original secret file (optional)",
                type=["txt", "wav", "avi", "mp4", "mkv", "mov", "png", "jpg", "jpeg", "gif", "bmp"],
                key="wiz_dec_original_upload",
            )
            if orig_up is not None:
                raw = orig_up.getvalue()
                uploaded_original_bytes = raw
                if payload_kind == "text":
                    try:
                        uploaded_original_text = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        st.caption("Could not read the uploaded original file as UTF-8 text.")

        if st.button("🔓 Decode / ডিকোড করুন", type="primary", disabled=stego_path_to_decode is None, key="wiz_decode_btn"):
            try:
                decoded = universal.decode(carrier, stego_path_to_decode, bit_depth=dec_bit_depth, mode=dec_mode, seed=dec_seed)
                st.success("✅ Decoding successful! / ডিকোডিং সফল হয়েছে!")

                original_text_ref = st.session_state.get("wiz_original_text", uploaded_original_text)
                original_bytes_ref = st.session_state.get("wiz_original_bytes", uploaded_original_bytes)

                if decoded.text is not None:
                    st.text_area("Extracted text / উদ্ধারকৃত টেক্সট", decoded.text, height=100, disabled=True)
                    if original_text_ref is not None:
                        st.json(full_text_report(original_text_ref, decoded.text))
                if decoded.audio_bytes is not None:
                    st.audio(decoded.audio_bytes, format="audio/wav")
                    rec_path = os.path.join(OUTPUTS_DIR, f"recovered_{decoded.audio_filename or 'audio.wav'}")
                    Path(rec_path).write_bytes(decoded.audio_bytes)
                    with open(rec_path, "rb") as f:
                        st.download_button("⬇ Download recovered audio", f, file_name=os.path.basename(rec_path), key="wiz_dl_audio")
                    if original_bytes_ref is not None:
                        st.json(full_audio_report(original_bytes_ref, decoded.audio_bytes))
                if decoded.video_bytes is not None:
                    rec_path = os.path.join(OUTPUTS_DIR, f"recovered_{decoded.video_filename or 'video.avi'}")
                    Path(rec_path).write_bytes(decoded.video_bytes)
                    st.video(rec_path)
                    with open(rec_path, "rb") as f:
                        st.download_button("⬇ Download recovered video", f, file_name=os.path.basename(rec_path), key="wiz_dl_video")
                    if original_bytes_ref is not None:
                        st.markdown("**Secret video comparison report / গোপন ভিডিও মিলের রিপোর্ট:**")
                        st.json(full_video_payload_report(original_bytes_ref, decoded.video_bytes))
                if decoded.image_bytes is not None:
                    rec_path = os.path.join(OUTPUTS_DIR, f"recovered_{decoded.image_filename or 'image.png'}")
                    Path(rec_path).write_bytes(decoded.image_bytes)
                    st.image(rec_path, caption="Recovered image")
                    with open(rec_path, "rb") as f:
                        st.download_button("⬇ Download recovered image", f, file_name=os.path.basename(rec_path), key="wiz_dl_image")
                    if original_bytes_ref is not None:
                        st.markdown("**Secret image comparison report / গোপন ছবি মিলের রিপোর্ট:**")
                        st.json(full_image_payload_report(original_bytes_ref, decoded.image_bytes))
            except (InvalidMagicError, InvalidVersionError, InvalidLengthError, ChecksumMismatchError) as exc:
                st.error(f"❌ Invalid or corrupted stego file, or wrong decode settings. / ভুল সেটিংস অথবা ফাইল ক্ষতিগ্রস্ত।\n\n{exc}")
            except PayloadError as exc:
                st.error(str(exc))
            except (AudioCarrierError, VideoCarrierError, TextCarrierError) as exc:
                st.error(str(exc))


def _stage_detect_choose_carrier():
    st.subheader("Step 1 / ধাপ ১: What type of file do you want to check?")
    st.caption("আপনি কোন ধরনের ফাইল যাচাই করতে চান?")

    cols = st.columns(len(CARRIER_LABELS))
    for col, (key, label) in zip(cols, CARRIER_LABELS.items()):
        with col:
            if st.button(label, use_container_width=True, key=f"wiz_detect_carrier_{key}"):
                st.session_state["wiz_detect_carrier"] = key
                st.session_state["wiz_stage"] = "detect_work"
                st.rerun()

    st.divider()
    if st.button("⬅ Back / পিছনে", key="wiz_detect_back_1"):
        st.session_state["wiz_stage"] = "welcome"
        st.rerun()


def _stage_detect_work():
    carrier = st.session_state["wiz_detect_carrier"]
    st.subheader(f"🔍 Detect hidden data in a {carrier} file")
    if st.button("⬅ Change file type / ফাইলের ধরন পরিবর্তন করুন", key="wiz_detect_back_2"):
        st.session_state["wiz_stage"] = "detect_choose_carrier"
        st.rerun()

    st.write(
        "Upload the file you suspect has hidden data. By default this tries the common "
        "settings automatically (1-bit and 2-bit, sequential mode). If it was encoded "
        "with random mode, untick auto-try and enter the exact bit depth / mode / seed."
    )
    st.caption(
        "যে ফাইলে গোপন তথ্য থাকতে পারে সন্দেহ করছেন সেটা আপলোড করুন। ডিফল্টভাবে এটা "
        "স্বয়ংক্রিয়ভাবে সাধারণ সেটিংস (1-bit ও 2-bit, sequential) চেষ্টা করবে। random mode "
        "হলে auto-try বন্ধ করে সঠিক bit depth/mode/seed দিন।"
    )

    if carrier == "image":
        st.warning(
            "⚠ **Important:** if this image was ever saved as JPEG, sent through WhatsApp/"
            "Messenger, or re-uploaded to social media *after* the data was hidden, the "
            "hidden data is permanently destroyed by that recompression — no detector can "
            "recover it. Always keep and share the exact PNG file the system generated.\n\n"
            "**গুরুত্বপূর্ণ:** এই ছবিটা যদি লুকানোর পর কখনো JPEG-এ সেভ হয়, WhatsApp/Messenger দিয়ে "
            "পাঠানো হয়, বা সোশ্যাল মিডিয়ায় আপলোড হয়, তাহলে লুকানো তথ্য স্থায়ীভাবে নষ্ট হয়ে যায় — "
            "কোনো ডিটেক্টর দিয়েই তা ফেরানো যায় না। সবসময় আসল PNG ফাইলটাই রাখুন ও শেয়ার করুন।"
        )

    up = st.file_uploader(f"{carrier.capitalize()} file to inspect", type=CARRIER_EXTS[carrier], key="wiz_detect_upload")

    if up is not None and carrier == "image" and Path(up.name).suffix.lower() in (".jpg", ".jpeg"):
        st.error(
            "❌ This file has a .jpg/.jpeg extension, which means it is (or has been) in a "
            "**lossy** format. If this is a re-saved/re-sent copy of the original PNG stego "
            "image, the hidden data is almost certainly already destroyed and detection will "
            "likely fail no matter what settings you try."
        )

    auto_try = st.checkbox("Try common settings automatically / স্বয়ংক্রিয়ভাবে চেষ্টা করুন", value=True, key="wiz_detect_auto")

    if auto_try:
        seed = None
        mode = "sequential"
        st.caption("Will try: bit depth 1 and 2, sequential mode.")
    else:
        bit_depth, mode, seed = embedding_settings_widget("wiz_detect")

    st.markdown("---")
    st.markdown("**Optional: compare against the original secret file / ঐচ্ছিক: আসল গোপন ফাইলের সাথে তুলনা করুন**")
    st.caption(
        "If you have the original secret file (before it was hidden), upload it here to see "
        "exactly what percentage matches after extraction. যদি আসল গোপন ফাইলটা থাকে, এখানে "
        "আপলোড করুন — নিষ্কাশনের পর কত শতাংশ মিলেছে তা দেখতে পাবেন।"
    )
    original_secret_file = st.file_uploader(
        "Original secret file (optional)", type=["txt", "wav", "avi", "mp4", "mkv", "mov", "png", "jpg", "jpeg", "gif", "bmp"],
        key="wiz_detect_original",
    )

    if st.button("🔍 Detect / খুঁজুন", type="primary", disabled=up is None, key="wiz_detect_btn"):
        path = save_uploaded_file(up, UPLOADS_DIR)
        decoded = None
        used_settings = None

        attempts = []
        if auto_try:
            attempts = [(1, "sequential", None), (2, "sequential", None)]
        else:
            attempts = [(bit_depth, mode, seed)]

        last_exc = None
        for try_bd, try_mode, try_seed in attempts:
            try:
                decoded = universal.decode(carrier, path, bit_depth=try_bd, mode=try_mode, seed=try_seed)
                used_settings = (try_bd, try_mode, try_seed)
                break
            except (InvalidMagicError, InvalidVersionError, InvalidLengthError, ChecksumMismatchError, PayloadError) as exc:
                last_exc = exc
                continue
            except (AudioCarrierError, VideoCarrierError, TextCarrierError) as exc:
                st.error(str(exc))
                return

        if decoded is None:
            st.warning(
                "❌ No hidden data found with the tried settings (or the data was destroyed "
                "by recompression -- see the warning above). Try unticking auto-try and "
                "entering exact bit depth / mode / seed if you know them.\n\n"
                "এই সেটিংসে কোনো লুকানো তথ্য পাওয়া যায়নি (অথবা তথ্যটা রিকমপ্রেশনে নষ্ট হয়ে গেছে)। "
                "নির্দিষ্ট bit depth/mode/seed দিয়ে চেষ্টা করুন।"
            )
            return

        st.success(f"✅ Hidden data found! Type: **{decoded.payload_type.name}** (bit depth={used_settings[0]}, mode={used_settings[1]})")
        st.balloons()

        if decoded.text is not None:
            st.markdown("**Hidden text found / লুকানো টেক্সট পাওয়া গেছে:**")
            st.text_area("", decoded.text, height=120, disabled=True, key="wiz_detect_text_result")
            if original_secret_file is not None:
                try:
                    original_text = original_secret_file.getvalue().decode("utf-8")
                    st.markdown("**Comparison with your original text / আসল টেক্সটের সাথে তুলনা:**")
                    st.json(full_text_report(original_text, decoded.text))
                except UnicodeDecodeError:
                    st.caption("Could not read the uploaded original file as UTF-8 text.")

        if decoded.audio_bytes is not None:
            st.markdown(f"**Hidden audio found / লুকানো অডিও পাওয়া গেছে:** {decoded.audio_filename}")
            st.audio(decoded.audio_bytes, format="audio/wav")
            rec_path = os.path.join(OUTPUTS_DIR, f"detected_{decoded.audio_filename or 'audio.wav'}")
            Path(rec_path).write_bytes(decoded.audio_bytes)
            with open(rec_path, "rb") as f:
                st.download_button("⬇ Download hidden audio", f, file_name=os.path.basename(rec_path), key="wiz_detect_dl_audio")
            if original_secret_file is not None:
                st.markdown("**Comparison with your original audio / আসল অডিওর সাথে তুলনা:**")
                st.json(full_audio_report(original_secret_file.getvalue(), decoded.audio_bytes))

        if decoded.video_bytes is not None:
            st.markdown(f"**Hidden video found / লুকানো ভিডিও পাওয়া গেছে:** {decoded.video_filename}")
            rec_path = os.path.join(OUTPUTS_DIR, f"detected_{decoded.video_filename or 'video.avi'}")
            Path(rec_path).write_bytes(decoded.video_bytes)
            st.video(rec_path)
            with open(rec_path, "rb") as f:
                st.download_button("⬇ Download hidden video", f, file_name=os.path.basename(rec_path), key="wiz_detect_dl_video")
            if original_secret_file is not None:
                st.markdown("**Comparison with your original video / আসল ভিডিওর সাথে তুলনা:**")
                st.json(full_video_payload_report(original_secret_file.getvalue(), decoded.video_bytes))

        if decoded.image_bytes is not None:
            st.markdown(f"**Hidden image found / লুকানো ছবি পাওয়া গেছে:** {decoded.image_filename}")
            rec_path = os.path.join(OUTPUTS_DIR, f"detected_{decoded.image_filename or 'image.png'}")
            Path(rec_path).write_bytes(decoded.image_bytes)
            st.image(rec_path)
            with open(rec_path, "rb") as f:
                st.download_button("⬇ Download hidden image", f, file_name=os.path.basename(rec_path), key="wiz_detect_dl_image")
            if original_secret_file is not None:
                st.markdown("**Comparison with your original image / আসল ছবির সাথে তুলনা:**")
                st.json(full_image_payload_report(original_secret_file.getvalue(), decoded.image_bytes))


# =====================================================================
# LEGACY / ADVANCED PAGES (kept for continuity with the previous version)
# =====================================================================

def page_multi_image_experiment():
    st.title("📊 Multi-Image Experiment (Thesis Comparison)")
    st.markdown(
        "Upload **several cover images** and embed the **same** secret text/audio/image "
        "into every one of them, then compare capacity, image quality, and recovery "
        "accuracy side by side. এই পাতায় একই গোপন তথ্য একাধিক ছবিতে বসিয়ে তুলনা করা যায়।"
    )

    image_files = st.file_uploader(
        "Cover images (upload multiple)", type=["png", "jpg", "jpeg", "gif", "bmp"], accept_multiple_files=True, key="multi_images"
    )
    payload_kind = st.radio("Secret data type", ["Text only", "Audio only", "Image only", "Text + Audio"], key="multi_payload_kind")
    secret_text = None
    audio_bytes = None
    audio_filename = "audio.wav"
    image_bytes = None
    image_filename = "image.png"

    if payload_kind in ("Text only", "Text + Audio"):
        secret_text = st.text_area("Secret text (same for all images)", height=100, key="multi_text")
    if payload_kind in ("Audio only", "Text + Audio"):
        audio_file = st.file_uploader("Secret WAV audio (same for all images)", type=["wav"], key="multi_audio")
        if audio_file is not None:
            audio_path = save_uploaded_file(audio_file, UPLOADS_DIR)
            audio_bytes = Path(audio_path).read_bytes()
            audio_filename = audio_file.name
    if payload_kind == "Image only":
        secret_image_file = st.file_uploader(
            "Secret image (same for all cover images) / গোপন ছবি (সব ছবির জন্য একই)",
            type=["png", "jpg", "jpeg", "gif", "bmp"], key="multi_secret_image",
        )
        if secret_image_file is not None:
            image_path = save_uploaded_file(secret_image_file, UPLOADS_DIR)
            image_bytes = Path(image_path).read_bytes()
            image_filename = secret_image_file.name

    bit_depth, mode, seed = embedding_settings_widget("multi_enc")

    if st.button("Run experiment across all images", key="multi_run_btn"):
        if not image_files:
            st.error("Please upload at least one cover image.")
        else:
            cover_paths = [save_uploaded_file(f, UPLOADS_DIR) for f in image_files]
            with st.spinner(f"Running experiment on {len(cover_paths)} image(s)..."):
                rows = run_multi_image_experiment(
                    cover_paths,
                    text=secret_text if payload_kind in ("Text only", "Text + Audio") else None,
                    audio_bytes=audio_bytes,
                    audio_filename=audio_filename,
                    image_bytes=image_bytes if payload_kind == "Image only" else None,
                    image_filename=image_filename,
                    bit_depth=bit_depth,
                    mode=mode,
                    seed=seed,
                    output_dir=OUTPUTS_DIR,
                )
            st.session_state["multi_results"] = rows
            st.success(f"Experiment complete for {len(rows)} image(s).")
            if payload_kind == "Image only":
                st.caption(
                    "Look at the 'secret_image_exact_byte_match' and "
                    "'secret_image_byte_accuracy_percent' columns to confirm the hidden "
                    "picture came back perfectly from every cover image, and the "
                    "'image_psnr_db'/'image_ssim' columns to see how much each cover "
                    "image itself changed (this will differ per image)."
                )

    if "multi_results" in st.session_state:
        rows = st.session_state["multi_results"]
        df = pd.DataFrame(rows)
        st.subheader("Results table")
        st.dataframe(df, use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            csv_buf = io.StringIO()
            df.to_csv(csv_buf, index=False)
            st.download_button("Download CSV", csv_buf.getvalue(), file_name="multi_image_results.csv", mime="text/csv")
        with col2:
            st.download_button("Download JSON", df.to_json(orient="records", indent=2), file_name="multi_image_results.json", mime="application/json")

        save_csv(rows, os.path.join(RESULTS_DIR, "multi_image_results.csv"))
        save_json(rows, os.path.join(RESULTS_DIR, "multi_image_results.json"))

        ok_df = df[df["status"] == "OK"] if "status" in df.columns else df
        if not ok_df.empty:
            st.subheader("Comparison charts")
            metric_options = [c for c in ["image_psnr_db", "image_mse", "image_ssim", "capacity_bytes", "image_modified_percent"] if c in ok_df.columns]
            for metric in metric_options:
                fig, ax = plt.subplots(figsize=(6, 3))
                plot_df = ok_df[ok_df[metric] != float("inf")]
                ax.bar(plot_df["cover_image"], plot_df[metric], color="#4C72B0")
                ax.set_ylabel(metric)
                ax.set_xlabel("Cover image")
                ax.set_title(f"{metric} across cover images")
                plt.xticks(rotation=30, ha="right")
                st.pyplot(fig)
                plt.close(fig)


def page_results_history():
    st.title("🗂️ Saved Experiment Results")
    csv_path = os.path.join(RESULTS_DIR, "multi_image_results.csv")
    json_path = os.path.join(RESULTS_DIR, "multi_image_results.json")

    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path)
        st.subheader("Last saved multi-image experiment")
        st.dataframe(df, use_container_width=True)
        with open(csv_path, "rb") as f:
            st.download_button("Download CSV", f, file_name="multi_image_results.csv")
        if os.path.exists(json_path):
            with open(json_path, "rb") as f:
                st.download_button("Download JSON", f, file_name="multi_image_results.json")
    else:
        st.info("No saved experiment results yet. Run one from the Multi-Image Experiment page.")


PAGES = {
    "🏠 Home (Hide / Detect)": page_wizard,
    "📊 Multi-Image Experiment": page_multi_image_experiment,
    "🗂️ Saved Results": page_results_history,
}


def main():
    st.sidebar.title("Navigation / নেভিগেশন")
    choice = st.sidebar.radio("Go to", list(PAGES.keys()))
    if choice == "🏠 Home (Hide / Detect)":
        if st.sidebar.button("🔄 Restart wizard / নতুন করে শুরু করুন"):
            reset_wizard()
            st.rerun()
    PAGES[choice]()


if __name__ == "__main__":
    main()
