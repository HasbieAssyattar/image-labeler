# Media Labeler

A desktop application built with Python and CustomTkinter for labeling images and videos. This tool supports local datasets and Google Drive integration.

## Features

- **Google Drive Integration**: Support for public Google Drive folders.
- **Video Support**: Playback for .mp4, .avi, .mov, and .mkv files.
- **Asynchronous Operations**: Background processing for smooth UI responsiveness.
- **Category Detection**: Automatically generates buttons based on subfolders in the destination directory.
- **Dark Theme**: Simple modern interface.

## Project Structure

- `labeler_app.py`: Main application code.
- `requirements.txt`: Dependencies.
- `temp/`: Default source folder.
- `hasil/`: Destination folder with category subfolders.

## Getting Started

### Prerequisites

- Python 3.8+

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/HasbieAssyattar/image-labeler.git
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Preparation

- **Local Mode**: Place media in the `temp/` folder.
- **Categories**: Create subfolders in the `hasil/` folder for each label.

### Usage

1. Run the application:
   ```bash
   python labeler_app.py
   ```
2. Select the source and destination folders.
3. Click category buttons to move/download files into respective folders.

## Dependencies

- customtkinter
- Pillow
- opencv-python
- requests
- gdown
