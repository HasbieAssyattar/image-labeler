# Image Labeler

A modern, fast, and dynamic image labeling tool built with Python and CustomTkinter. Designed to help curators sort large datasets quickly into custom categories.

## ✨ Features
- **Dynamic Category Buttons**: Automatically creates buttons based on subfolders in the `hasil/` directory.
- **Modern UI**: Dark-themed, responsive interface using CustomTkinter.
- **Fast Workflow**: Move images to categories with a single click.
- **Image Preview**: High-quality previews with aspect ratio preservation.
- **Safe Operations**: Ensures files are closed before moving to avoid locking issues on Windows.

## 🚀 Getting Started

### Prerequisites
- Python 3.7+
- Pip

### Installation
1. Clone the repository:
   ```bash
   git clone <your-repo-url>
   cd image-labeler
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Usage
1. Place your images in the `temp/` folder.
2. Create category subfolders inside the `hasil/` folder (e.g., `dogs/`, `cats/`).
3. Run the app:
   ```bash
   python labeler_app.py
   ```
4. Click the category buttons to move images. Use **Back** or **Skip Next** for navigation.

## 📂 Folder Structure
- `temp/`: Source images for labeling.
- `hasil/`: Destination folders for categorized images.
- `labeler_app.py`: Main application script.

## 📝 License
MIT
