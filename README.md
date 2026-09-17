# Advanced Steganography System

A thesis-oriented research prototype for **LSB-based steganography across image,
audio, video, and plain text files** -- supporting the full 16 carrier x payload
combinations (Image, Audio, Video, Text as the cover; Text, Audio, Video, Image
as the hidden data), a bilingual (English/Bangla) guided Hide/Detect wizard,
and rigorous, real (non-hard-coded) quantitative comparison covering both
classic metrics (MSE/PSNR/SSIM) and an extended, photo/audio/video-parameter-
style breakdown (brightness, contrast, saturation, sharpness, RMS level,
spectral centroid, and more).

## What's new in this version

- **Runs fully offline / without WiFi.** A `.streamlit/config.toml` file
  disables Streamlit's first-run telemetry/"Welcome" network call, which was
  previously blocking startup when no internet connection was available. The
  app itself only ever talks to `localhost` -- it never needed the internet to
  function, only to check in with Streamlit's servers on first run.
- **Text as a carrier.** Hide data inside a plain `.txt` file using invisible
  zero-width Unicode characters -- the visible text is 100% unchanged to a
  human reader or a plain-text diff.
- **Image as a payload.** Hide an image file inside any carrier (previously
  only text/audio/video could be hidden; now images can be too).
- **Full 4x4 = 16 combinations**: every carrier (Image/Audio/Video/Text)
  paired with every payload (Text/Audio/Video/Image), including same-type
  pairs like image-in-image and text-in-text.
- **Extended quality-parameter reports.** Beyond MSE/PSNR/SSIM, the system now
  computes and displays, for every image/audio/video encode:
    - **Image**: brightness, exposure, contrast, saturation, vibrance, hue,
      color temperature, sharpness, highlights %, shadows %, vignette ratio,
      fade index, dehaze index (Dark Channel Prior), enhance index.
    - **Audio**: RMS level (dBFS), peak amplitude, crest factor, zero-crossing
      rate, spectral centroid, spectral bandwidth, low/mid/high frequency
      energy split, dynamic range, silence percentage.
    - **Video**: the same image parameters averaged across sampled frames,
      plus a temporal (frame-to-frame) difference metric.

  Every parameter is shown as **original value, stego value, absolute
  difference, and percent difference** -- so you can see exactly how much (or
  how little) each property shifted after embedding.

## Features

- **Text-in-any-carrier**, **audio-in-any-carrier**, **video-in-any-carrier**,
  **image-in-any-carrier**: UTF-8 text (English, Bangla, numbers, symbols,
  emoji), WAV audio, AVI/MP4 video, and PNG/JPG images, all byte-exact on
  recovery.
- **Combined mode** (image carrier only): text + audio in one stego image.
- **Configurable LSB engine**: 1-bit or 2-bit depth; sequential or seeded
  pseudo-random ordering -- generalized to work identically on image pixels,
  audio sample bytes, video frame pixels, and text character-slots.
- **Text comparison**: exact match, character accuracy, byte accuracy,
  sequence similarity, error count, missing/extra characters (via `difflib`).
- **Classic image quality comparison**: MSE, PSNR, SSIM, modified/unchanged
  pixel percentages, and a visual difference map.
- **Extended quality comparison**: see "What's new" above -- a full
  photo/audio/video-parameter-style breakdown for every encode.
- **Audio comparison**: byte-exact match, byte accuracy, checksum match, and
  signal-level MSE/RMSE/correlation/SNR.
- **Multi-image experiments**: embed the *same* secret text/audio into several
  cover images at once and get a comparison table + charts.
- **Bilingual guided wizard** (Home page): Welcome screen -> Hide Data /
  Detect Hidden Data -> carrier & payload choice -> encode/decode UI, all in
  English and Bangla side by side.
- **Detect Hidden Data mode**: upload any suspicious file and the system
  attempts to extract and reveal what's hidden inside it, using SHA-256
  checksum validation to reliably tell "nothing hidden / wrong settings"
  apart from "real hidden data found".
- **Automated test suite**: 40 tests covering round-trip correctness for all
  16 combinations, error handling, wrong-settings detection, and the extended
  metric modules.

## Project structure

```text
advanced_steganography_system/
|-- app.py                        # Streamlit GUI (entry point) -- bilingual wizard + advanced pages
|-- requirements.txt
|-- README.md
|-- .streamlit/
|   `-- config.toml               # disables telemetry so the app runs fully offline
|-- src/
|   |-- steganography/
|   |   |-- lsb.py                  # core LSB embed/extract -- carrier-agnostic (bit depth, sequential/random)
|   |   |-- payload.py              # binary payload format (header, checksum, TEXT/AUDIO/VIDEO/IMAGE/COMBINED types)
|   |   |-- image_io.py             # image load/save (PNG/JPG/GIF/BMP -> PNG)
|   |   |-- audio_carrier.py        # use WAV audio as the carrier (embed in sample low-bytes)
|   |   |-- video_carrier.py        # use video as the carrier (embed in frame pixels, lossless FFV1 output)
|   |   |-- text_carrier.py         # NEW: use plain text as the carrier (invisible zero-width Unicode chars)
|   |   |-- universal.py            # unified encode/decode/capacity dispatch across all 16 combinations
|   |   |-- encoder.py              # legacy image-carrier convenience wrappers (text/audio/combined)
|   |   `-- decoder.py              # legacy image-carrier convenience wrappers
|   |-- analysis/
|   |   |-- image_metrics.py        # MSE, PSNR, SSIM, pixel change stats
|   |   |-- extended_image_metrics.py  # NEW: brightness/contrast/saturation/sharpness/etc.
|   |   |-- extended_audio_metrics.py  # NEW: RMS/peak/spectral centroid/frequency bands/etc.
|   |   |-- extended_video_metrics.py  # NEW: frame-averaged image params + temporal difference
|   |   |-- text_metrics.py         # exact match, char/byte accuracy, sequence similarity
|   |   |-- audio_metrics.py        # byte-level + signal-level audio comparison
|   |   `-- experiment.py           # single & multi-image experiment orchestration
|   |-- audio/
|   |   `-- audio_processor.py      # WAV read/write/validate (soundfile)
|   `-- utils/
|       |-- file_utils.py           # dirs, CSV/JSON save, size formatting
|       `-- validators.py           # format/capacity validation
|-- results/                      # saved experiment CSV/JSON (auto-created)
|-- outputs/                      # generated stego files, recovered files (auto-created)
|-- uploads/                      # files uploaded via the GUI (auto-created)
`-- tests/
    |-- test_system.py            # original 14 tests
    |-- test_universal.py         # 20 tests covering all 16 carrier x payload combinations
    `-- test_extended_metrics.py  # NEW: 6 tests for the extended metric modules
```

## Payload format

```
MAGIC (4 bytes, "STG2") | VERSION (1 byte) | PAYLOAD_TYPE (1 byte) |
PAYLOAD_LENGTH (4 bytes) | SHA-256 CHECKSUM (32 bytes) | DATA
```

`PAYLOAD_TYPE`: `0`=text, `1`=audio, `2`=combined (text+audio, image carrier
only), `3`=video, `4`=image. The checksum covers the `DATA` section only, so
any corruption or wrong decode settings (wrong bit depth, mode, seed, or a
clean file with nothing hidden) is detected immediately -- this is exactly
what powers the **Detect Hidden Data** feature.

## How each carrier stores data losslessly

| Carrier | Technique | Lossless output format |
|---|---|---|
| Image | LSB of each RGB(A) channel byte | PNG |
| Audio (WAV) | LSB of the *low byte* of each 16-bit PCM sample | WAV (PCM_16) |
| Video | LSB of each RGB channel byte, across all frames | AVI (FFV1 codec) |
| Text | One invisible zero-width Unicode character inserted per hidden bit-group | Plain UTF-8 `.txt` |

Video, audio, and text all reuse the same generalized LSB/bit-group engine as
images, so bit depth, sequential/random mode, and seed behave identically
everywhere.

## Setup (VS Code / Windows)

1. Extract this folder and open it in VS Code (**File -> Open Folder**, select
   the folder that directly contains `app.py`).
2. Open a terminal and confirm you're in the right folder:
   ```bash
   dir
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the automated test suite:
   ```bash
   python -m unittest discover tests -v
   ```
   You should see `Ran 40 tests ... OK`.
5. Launch the GUI:
   ```bash
   python -m streamlit run app.py
   ```
   (Use `python -m streamlit run app.py` instead of plain `streamlit run app.py`
   if Windows says `streamlit` is not recognized -- this happens when pip's
   Scripts folder isn't on your PATH; either form works identically.)

   Thanks to `.streamlit/config.toml`, this starts immediately without asking
   for an email or needing an internet/WiFi connection.

## Windows network permission prompt

If Windows Firewall asks whether to allow Python to access networks on
**Private networks**, **Public networks**, or both -- checking **Private
networks** only is sufficient and recommended. The app itself runs entirely
on `localhost` (your own machine) and does not need network access to work;
this prompt appears simply because Python's underlying web-server library
requests a socket, which Windows flags by default.

## Using the wizard (Home page)

1. **Welcome screen** -> choose **Hide Data** or **Detect Hidden Data**.
2. **Hide Data** -> choose the carrier (Image/Audio/Video/Text), then the
   payload (Text/Audio/Video/Image) -- this selects one of the 16
   combinations. Upload the cover file, provide the secret text/file, choose
   bit depth and mode, click **Encode**. The extended quality-parameter table
   appears automatically. Then use **Decode & Verify** (same settings) to
   confirm perfect recovery.
3. **Detect Hidden Data** -> choose the file type to inspect, upload the
   suspicious file, provide the settings you suspect it was encoded with (or
   try the defaults first), click **Detect**.
4. **Multi-Image Experiment** and **Saved Results** (sidebar) remain
   available for thesis-style comparison tables and charts.

## Example command-line workflow (without the GUI)

```python
import sys
sys.path.insert(0, "src")
from steganography import universal

# Hide text inside a plain text file (invisible zero-width characters)
cover_text_path = "uploads/cover.txt"  # should be a reasonably long .txt file
payload = universal.build_payload_for("text", text="Bangladesh is beautiful.")
universal.encode("text", cover_text_path, payload, "outputs/stego.txt", bit_depth=1, mode="sequential")
decoded = universal.decode("text", "outputs/stego.txt", bit_depth=1, mode="sequential")
print(decoded.text)

# Hide an image inside a video
image_bytes = open("uploads/secret.png", "rb").read()
payload2 = universal.build_payload_for("image", secret_bytes=image_bytes, secret_filename="secret.png")
universal.encode("video", "uploads/cover.avi", payload2, "outputs/stego.avi", bit_depth=2, mode="sequential")
decoded2 = universal.decode("video", "outputs/stego.avi", bit_depth=2, mode="sequential")
open("outputs/recovered.png", "wb").write(decoded2.image_bytes)
```

### Computing extended quality reports from the command line

```python
import sys
sys.path.insert(0, "src")
from steganography.image_io import load_cover_image
from analysis.extended_image_metrics import compare_extended_image_metrics

cover = load_cover_image("uploads/cover.png")
stego = load_cover_image("outputs/stego.png")
report = compare_extended_image_metrics(cover, stego)
for name, row in report.items():
    print(f"{name:20s} orig={row['original']:>10} stego={row['stego']:>10} diff%={row['percent_difference']}")
```

## Notes on lossy formats

JPEG, MP4/H.264, and MP3 all use lossy compression, which would destroy
LSB-embedded bits on save. This system always **reads** these formats when
used as a cover, but **saves the stego output losslessly** (PNG for images,
PCM WAV for audio, FFV1-codec AVI for video) -- never re-compressed.

## Interpreting percent-difference for near-zero baselines

A few extended metrics (e.g. audio's `high_freq_energy_percent`, or video's
`spectral_bandwidth`) can show a *large relative percent difference* even
though the *absolute* change is tiny. This happens when the original value is
very close to zero: LSB embedding adds a barely-measurable amount of
broadband noise, and dividing a small absolute change by a near-zero baseline
inflates the percentage. Always check the `absolute_difference` column
alongside `percent_difference` -- this is expected, honest behavior of LSB
steganography, not a bug.

## Error handling

The system raises clear, specific errors for:
- Missing or corrupted image/audio/video/text files.
- Unsupported file formats.
- Insufficient carrier capacity for the given payload and bit depth (for text
  carriers, capacity = number of characters in the cover text).
- Wrong decode settings (bit depth / mode / seed) or a genuinely corrupted/
  clean stego file -- detected via SHA-256 checksum validation. This same
  mechanism powers the Detect mode.
- Invalid WAV/video files, or non-UTF-8 text files.

## Thesis-relevant guarantees

- All metrics (classic and extended) are computed directly from the actual
  embedded/extracted data -- nothing is hard-coded.
- LSB recovery is lossless by design (verified by SHA-256), so recovery
  accuracy will legitimately be 100% across different cover files.
- Carrier-quality metrics naturally vary per cover file because they depend
  on that file's own content -- the multi-image experiment and the extended
  metric reports both demonstrate this directly with real numbers.
- The extended metrics are honestly documented: some (dehaze index, enhance
  index) are clearly labeled as self-defined or classic-but-approximate
  proxies rather than presented as universally standardized measurements.
