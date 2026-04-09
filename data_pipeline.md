## 4.2 Data Pipeline Design

The project's Data Pipeline is divided into 3 main phases to ensure data is ready for processing:

1. **Ingestion & Pre-processing**: Receives image files (JPG/PNG) or PDFs (via `pdf2image`), then uses OpenCV to adjust contrast and resize the image to fit the input requirements of MangaLMM.

2. **Layout Analysis (VLM Stage)**: Uses the MangaLMM (Qwen2.5-VL) model to detect the pixels of speech bubbles and determine the reading order from right to left.

3. **Text Processing & Translation**: Extracts the Japanese text and forwards it to the fine-tuned Qwen3 model to translate it into Thai.

```mermaid
flowchart TD
    %% Phase 1: Ingestion & Pre-processing
    subgraph Phase1 [1. Ingestion & Pre-processing]
        direction TB
        Input(["Receive image files JPG, PNG
        or PDF"])

        ConvertPDF["Convert PDF to Image
        (pdf2image)"]

        OpenCVPreprocess["Adjust Contrast
        and Resize Image
        using OpenCV"]

        Input --> ConvertPDF
        Input --> OpenCVPreprocess
        ConvertPDF --> OpenCVPreprocess
    end

    %% Phase 2: Layout Analysis (VLM Stage)
    subgraph Phase2 [2. Layout Analysis VLM Stage]
        direction TB
        MangaLMM["Process with MangaLMM
        (Qwen2.5-VL) model"]

        DetectBubble["Identify speech bubble
        pixels"]

        ReadingOrder["Determine reading order
        (Right to Left)"]

        OpenCVPreprocess --> MangaLMM
        MangaLMM --> DetectBubble
        MangaLMM --> ReadingOrder
    end

    %% Phase 3: Text Processing & Translation
    subgraph Phase3 [3. Text Processing & Translation]
        direction TB
        ExtractJP["Extract Japanese
        Text"]

        Qwen3Translate["Translate to Thai
        using Qwen3 (Fine-tuned)"]

        OutputTH(["Obtain translated Thai
        text output"])

        DetectBubble --> ExtractJP
        ReadingOrder --> ExtractJP
        ExtractJP --> Qwen3Translate
        Qwen3Translate --> OutputTH
    end
```
