# Manga Translator System Architecture

This document describes the high-level architecture of the Manga Translator application. It breaks down the system into the user interface, core processing elements, external AI services, and file storage components.

```mermaid
graph TD
    User([User])

    %% --- Streamlit Application Layer ---
    subgraph StreamlitApp["User Interface Layer (Streamlit App)"]
        UI["Web UI Interface(Settings, Output Preview, Download)"]
        BatchRunner["Pipeline Batch Controller"]
    end

    %% --- Processing Core Layer ---
    subgraph ProcessingCore["File & Image Processing Core"]
        PDFEngine["PDF Parser(pdf2image + Poppler)"]
        ImageProcessing["Image Processor(Load & Compress - PIL)"]
        RenderEngine["Artifact Render Engine(Draw Boxes, Whitefill, Render Font)"]
        Aggregator["Text & Metadata Aggregator(JSON Combiner)"]
    end

    %% --- Microservice Integrations ---
    subgraph APIIntegration["API Integration Layer"]
        OCRClient["OCR HTTP Client"]
        TranslClient["Translation HTTP Client"]
    end

    %% --- External AI Services (Endpoints configured in UI) ---
    subgraph AIServices["External AI Services"]
        OCRService["Manga OCR API(Text Detection & Bounding Boxes)"]
        TranslationService["LLM Translation API(JP to TH text translation)"]
    end

    %% --- Storage Layer ---
    subgraph FileStorage["File Storage System"]
        Inputs[("Input Files(Uploads, /images, /pdfs)")]
        Outputs[("Output Results(/output_results & JSON pairs)")]
    end

    %% --- Relationships & Data Flow ---
    User -->|Configure, Select Files & Run| UI
    UI -->|Triggers process| BatchRunner

    BatchRunner -->|Fetch Inputs| Inputs
    BatchRunner -->|PDF Files| PDFEngine
    BatchRunner -->|Standard Images| ImageProcessing

    PDFEngine -->|Page as PIL Image| ImageProcessing

    ImageProcessing -->|Compressed Image| OCRClient
    OCRClient <-->|"Request / JSON (Boxes & Text)"| OCRService

    OCRClient -->|Extracted raw JP sentences| TranslClient
    TranslClient <-->|"JP Text / Output TH Text"| TranslationService

    TranslClient -->|JP & translated TH text+ Box Coordinates| RenderEngine
    ImageProcessing -->|Original Image Base| RenderEngine

    RenderEngine -.->|1. analyzed.jpg2. whitefill.jpg3. translated.jpg| Outputs
    RenderEngine --> Aggregator

    Aggregator -.->|Save all_files_jp_th.json| Outputs
    Aggregator -->|Process Complete| UI

    Outputs -.->|Preview Downloads & Visuals| UI

    %% Styling
    classDef External fill:#326ce5,stroke:#fff,stroke-width:2px,color:#fff;
    classDef Processing fill:#ea5a0b,stroke:#fff,stroke-width:2px,color:#fff;
    classDef Storage fill:#5b6a7a,stroke:#fff,stroke-width:2px,color:#fff;
    classDef UI fill:#41b2a9,stroke:#fff,stroke-width:2px,color:#fff;

    class OCRService,TranslationService External;
    class PDFEngine,ImageProcessing,RenderEngine,Aggregator Processing;
    class Inputs,Outputs Storage;
    class UI,BatchRunner UI;
```

## Key Architectural Layers

1. **User Interface Layer**: Powered by `streamlit_app.py`, providing user controls for API configuration, file uploading (`.pdf`, `.jpg`, `.png`), and displaying interactive outputs.
2. **File & Image Processing Core**: A local engine managing file formatting (`poppler`/`pdf2image`, `PIL`), background clearing (whitefill), and calculating/drawing localized text boxes.
3. **API Integration Layer**: HTTP clients connecting the Streamlit frontend with remote AI services.
4. **External AI Services**: Independent REST endpoints handling the heavy lifting: Manga OCR API for text detection and LLM Translation API for Japanese-to-Thai translation.
5. **Storage System**: Reads input files from specified directories or temp uploads and writes results (debug images, final translated images, and JSON data) to the `output_results/` directory.
