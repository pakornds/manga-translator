# manga-translator

Translates Japanese manga pages into Thai. The system finds speech bubbles and reading order with MangaLMM (Qwen2.5-VL), translates the text with a fine-tuned Qwen3 model, and renders the Thai text back onto the page. A Streamlit app runs the pipeline on PDFs and images.

## Paper

An End-to-End AI System for Translating Japanese Manga into Thai (IEEE Xplore): https://ieeexplore.ieee.org/document/11608395

## Installation

Please install Poppler to enable PDF processing depending on your OS:

### Windows

- Download and install from: https://github.com/oschwartz10612/poppler-windows
- Extract the zip file and add the `bin` folder to your system PATH.

### Linux (Ubuntu/Debian)

```bash
sudo apt-get install poppler-utils
```

### macOS

```bash
brew install poppler
```

## Citation

```
@article{hinami_aaai_2021,
    author={Ryota Hinami and Shonosuke Ishiwatari and Kazuhiko Yasuda and Yusuke Matsui},
    title={Towards Fully Automated Manga Translation},
    booktitle={Proceedings of the AAAI Conference on Artificial Intelligence},
    year={2021}
}
```
