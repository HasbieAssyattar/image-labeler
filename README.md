# Image Labeler Cloud (v2.0) 🚀

A modern, fast, and feature-rich desktop application built with Python and **CustomTkinter** for high-performance image dataset curation and labeling. This application supports both local datasets and seamless integration with public **Google Drive** folders, utilizing asynchronous multi-threading to ensure a fluid, lag-free user experience.

---

## ✨ Features

- **☁️ Google Drive Integration**: Paste any public Google Drive folder link or ID to directly stream, label, and download images on the fly.
- **⚡ Asynchronous & Multi-Threaded**: Heavy operations (like connecting to GDrive and fetching images) run in the background. The user interface remains 100% responsive without freezing.
- **🖼️ Smart Thumbnail Preview**: Downloads low-resolution previews first for lightning-fast cloud curation, saving bandwidth and time.
- **📂 Dynamic Category Auto-Detection**: Scans your destination (`hasil/`) folder and dynamically generates custom category buttons on the UI dashboard.
- **🎨 Premium Dark Theme**: Sleek, modern interface using CustomTkinter with custom aspect-ratio-preserving image renders.
- **🔄 Dual Modes**: Easily switch between local offline labeling and cloud-connected labeling.

---

## 📂 Folder Structure

```text
├── labeler_app.py      # Main application script
├── requirements.txt    # Python dependencies
├── temp/               # Default local source folder for images
└── hasil/              # Destination folder containing category subfolders
    ├── category_a/     # Subfolder representing Category A
    └── category_b/     # Subfolder representing Category B
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.8+
- Active internet connection (for Cloud mode)

### 1. Installation

Clone the repository and install the required dependencies:

```bash
git clone https://github.com/HasbieAssyattar/image-labeler.git
cd image-labeler
pip install -r requirements.txt
```

### 2. Prepare Directories

- **Local Mode**: Place your unclassified images in the `temp/` folder.
- **Categories**: Create subdirectories inside the `hasil/` folder for each label you want (e.g., `dog`, `cat`, `bird`). The app will automatically detect these and generate buttons for them!

### 3. Run the Application

```bash
python labeler_app.py
```

---

## 🛠️ Usage

### 🔹 Local Curation
1. Under the **Local** tab, click **Select Local Folder** (defaults to `temp/`).
2. Click **Select Destination** to choose where categorized images go (defaults to `hasil/`).
3. Click any of the category buttons to immediately classify and move the image to that folder.

### 🔹 Cloud (Google Drive) Curation
1. Select the **GDrive** tab.
2. Paste your public Google Drive folder URL or ID.
3. Click **Connect GDrive** (accept the prompt).
4. The app will stream thumbnails instantly. When you click a category, it downloads the full-resolution image directly into that category folder!

---

## 📦 Dependencies

- `customtkinter`: Modern UI widgets.
- `Pillow` (PIL): Image loading and aspect-ratio preservation.
- `requests`: Fetching cloud images and GDrive scraping.
- `gdown`: Robust Google Drive downloading.

---

## 📝 License

Distributed under the MIT License. See `LICENSE` for more information.
