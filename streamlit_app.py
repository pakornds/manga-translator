import os
import glob
import json
import io
import time
import tempfile
from pathlib import Path

import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageStat
from pdf2image import convert_from_path

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".pdf"}
# raw string litera
DEFAULT_FONT_PATH = (
    r"C:\Users\pakor\AppData\Local\Microsoft\Windows\Fonts\LayijiMahaniyomV1.ttf"
)
# If adding Poppler to PATH doesn't work, set this to the literal path of your Poppler bin folder
POPPLER_PATH = r"C:\poppler-25.12.0\Library\bin"

TONE_MARK_VERTICAL_SCALE = 0.65
LINE_SPACING_PX = 4
TOP_MARGIN_PX = 20
RIGHT_PADDING_EXTRA_PX = 10
TOP_PADDING_RATIO = 0.5
DEFAULT_OCR_CONNECT_TIMEOUT_SEC = 20
DEFAULT_OCR_READ_TIMEOUT_SEC = 300
DEFAULT_OCR_RETRIES = 2
DEFAULT_OCR_JPEG_QUALITY = 95


def debug_log(stage, message):
    """
    Print a structured debug message tagged by pipeline stage.

    Args:
        stage (str): The pipeline stage.
        message (str): The debug message to print.

    Returns:
        None
    """
    print(f"[DEBUG][{stage}] {message}")


def is_streamlit_run_context():
    """
    Return True when running inside a Streamlit script execution context.

    Args:
        None

    Returns:
        bool: True if inside Streamlit context, False otherwise.
    """
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        return get_script_run_ctx() is not None
    except Exception:
        return False


def collect_input_files(inputs):
    """
    Collect valid image/PDF files from explicit paths, folders, and glob patterns.

    Args:
        inputs (list): The list of input paths, folders or glob patterns.

    Returns:
        list: The list of collected unique file paths.
    """
    debug_log("INPUT", f"Collecting files from {len(inputs)} input item(s)")
    collected = []

    for item in inputs:
        item = item.strip()
        if not item:
            continue

        if os.path.isdir(item):
            for name in sorted(os.listdir(item)):
                path = os.path.join(item, name)
                ext = os.path.splitext(path)[1].lower()
                if os.path.isfile(path) and ext in ALLOWED_EXT:
                    collected.append(path)
        elif any(ch in item for ch in ["*", "?", "["]):
            for path in sorted(glob.glob(item)):
                ext = os.path.splitext(path)[1].lower()
                if os.path.isfile(path) and ext in ALLOWED_EXT:
                    collected.append(path)
        elif os.path.isfile(item):
            ext = os.path.splitext(item)[1].lower()
            if ext in ALLOWED_EXT:
                collected.append(item)

    return list(dict.fromkeys(collected))


def run_ocr(file_path, ocr_api_url):
    """
    Upload a file path directly to the OCR API and return parsed JSON.

    Args:
        file_path (str): The path to the file to upload.
        ocr_api_url (str): The URL of the OCR API.

    Returns:
        dict: The parsed JSON data from the OCR API.
    """
    debug_log("OCR", f"Uploading file path: {file_path}")
    lower = file_path.lower()
    if lower.endswith(".pdf"):
        mime_type = "application/pdf"
    elif lower.endswith(".png"):
        mime_type = "image/png"
    else:
        mime_type = "image/jpeg"

    headers = {"ngrok-skip-browser-warning": "true"}

    with open(file_path, "rb") as fh:
        files = {"file": (os.path.basename(file_path), fh, mime_type)}
        response = requests.post(ocr_api_url, files=files, headers=headers, timeout=300)

    response.raise_for_status()
    data = response.json()
    if data.get("status") != "success":
        raise ValueError(f"OCR server returned non-success response: {data}")
    return data


def run_ocr_for_pil_image(
    image,
    upload_name,
    ocr_api_url,
    connect_timeout=DEFAULT_OCR_CONNECT_TIMEOUT_SEC,
    read_timeout=DEFAULT_OCR_READ_TIMEOUT_SEC,
    max_retries=DEFAULT_OCR_RETRIES,
    jpeg_quality=DEFAULT_OCR_JPEG_QUALITY,
):
    """
    Upload a PIL image to OCR API with retry/backoff and timeout controls.

    Args:
        image (PIL.Image.Image): The PIL image to upload.
        upload_name (str): The name to use for the uploaded file.
        ocr_api_url (str): The URL of the OCR API.
        connect_timeout (int): The connection timeout in seconds.
        read_timeout (int): The read timeout in seconds.
        max_retries (int): The maximum number of retry attempts.
        jpeg_quality (int): The JPEG compression quality.

    Returns:
        dict: The parsed JSON data from the OCR API.
    """
    debug_log("OCR", f"Uploading in-memory image: {upload_name}")
    headers = {"ngrok-skip-browser-warning": "true", "Connection": "close"}

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=int(jpeg_quality))
    # Cache bytes once so each retry can rebuild a fresh readable stream.
    files_payload = buffer.getvalue()

    last_error = None
    for attempt in range(max(1, int(max_retries)) + 1):
        buffer = io.BytesIO(files_payload)
        files = {"file": (f"{upload_name}.jpg", buffer, "image/jpeg")}
        debug_log(
            "OCR",
            (
                f"Attempt {attempt + 1}/{max(1, int(max_retries)) + 1} -> {ocr_api_url} "
                f"(connect={connect_timeout}s, read={read_timeout}s)"
            ),
        )
        try:
            response = requests.post(
                ocr_api_url,
                files=files,
                headers=headers,
                timeout=(connect_timeout, read_timeout),
            )
            response.raise_for_status()
            data = response.json()
            break
        except requests.exceptions.Timeout as exc:
            last_error = exc
            debug_log("ERROR", f"OCR timeout for {upload_name}: {exc}")
        except requests.exceptions.RequestException as exc:
            last_error = exc
            debug_log("ERROR", f"OCR request failed for {upload_name}: {exc}")

        if attempt < max(1, int(max_retries)):
            # Small linear backoff helps transient ngrok/model spikes recover.
            backoff = min(5, attempt + 1)
            debug_log("OCR", f"Retrying after {backoff}s")
            time.sleep(backoff)
    else:
        raise TimeoutError(
            "OCR request failed after retries. Check OCR API health/network or increase timeout."
        ) from last_error

    if data.get("status") != "success":
        raise ValueError(f"OCR server returned non-success response: {data}")
    return data


def run_translation(sentences, translation_api_url):
    """
    Translate Japanese sentences one-by-one via the translation API.

    Args:
        sentences (list): The list of Japanese sentences.
        translation_api_url (str): The URL of the translation API.

    Returns:
        list: The list of translated sentences.
    """
    debug_log("TRANSLATE", f"Translating {len(sentences)} sentence(s)")
    headers = {"ngrok-skip-browser-warning": "true"}
    translated = []

    for idx, sentence in enumerate(sentences, start=1):
        payload = {"japanese_text": sentence}
        debug_log("TRANSLATE", f"Request {idx}/{len(sentences)}")
        response = requests.post(
            translation_api_url, json=payload, headers=headers, timeout=120
        )
        response.raise_for_status()
        result = response.json()
        translated.append(result.get("translated_text", ""))

    return translated


def load_font(font_path, size):
    """
    Load a TrueType font and fallback to PIL default if unavailable.

    Args:
        font_path (str): The path to the font file.
        size (int): The font size.

    Returns:
        PIL.ImageFont.FreeTypeFont | PIL.ImageFont.ImageFont: The loaded font.
    """
    try:
        return ImageFont.truetype(font_path, size)
    except OSError:
        return ImageFont.load_default()


def text_size(draw, text, font):
    """
    Measure rendered text width and height for the given font.

    Args:
        draw (PIL.ImageDraw.Draw): The drawing context.
        text (str): The text to measure.
        font (PIL.ImageFont.FreeTypeFont): The font to use for measurement.

    Returns:
        tuple: A tuple containing the width and height of the text (in pixels).
    """
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def compute_line_metrics(draw, font, line_spacing=0, tone_mark_scale=1.0):
    """
    Compute rendered line height and per-line step after scaling/spacing.

    Args:
        draw (PIL.ImageDraw.Draw): The drawing context.
        font (PIL.ImageFont.FreeTypeFont): The font to use for measurement.
        line_spacing (int): The additional space between lines.
        tone_mark_scale (float): The vertical scale to apply for tone marks.

    Returns:
        tuple: A tuple containing the rendered line height and the line step size.
    """
    _, base_line_h = text_size(draw, "Ag", font)
    base_line_h = max(1, base_line_h)
    rendered_line_h = max(1, int(round(base_line_h * max(0.5, tone_mark_scale))))
    line_step = rendered_line_h + max(0, int(line_spacing))
    return rendered_line_h, max(1, line_step)


def wrap_text_for_box(draw, text, font, max_width):
    """
    Wrap Thai text at word boundaries using PyThaiNLP newmm tokenization.

    Breaking at word boundaries (rather than raw characters or TCC clusters)
    produces more natural, readable lines.  font.getlength() is used for
    sub-pixel-accurate measurement.  Falls back to whitespace splitting when
    pythainlp is unavailable.

    Args:
        draw (PIL.ImageDraw.Draw): The drawing context (unused, kept for
            interface compatibility).
        text (str): The text to wrap.
        font (PIL.ImageFont.FreeTypeFont): The font to use for measurement.
        max_width (int): The maximum width of a line in pixels.

    Returns:
        list: The list of wrapped text lines.
    """
    if not text:
        return []

    try:
        from pythainlp import word_tokenize

        words = word_tokenize(text, engine="newmm")
    except ImportError:
        words = text.split() or [text]

    lines = []
    current = ""

    for word in words:
        candidate = current + word
        if font.getlength(candidate) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


def fit_and_wrap_text(
    draw,
    text,
    font_path,
    max_width,
    max_height,
    start_size=48,
    min_size=14,
    line_spacing=0,
    tone_mark_scale=1.0,
):
    """
    Find a fitting font size and wrapped lines for a constrained text box.

    Args:
        draw (PIL.ImageDraw.Draw): The drawing context.
        text (str): The text to format.
        font_path (str): The path to the font file.
        max_width (int): The maximum width of the box.
        max_height (int): The maximum height of the box.
        start_size (int): The starting font size to check.
        min_size (int): The minimum allowable font size.
        line_spacing (int): The additional space between lines.
        tone_mark_scale (float): The vertical scale.

    Returns:
        tuple: A tuple containing the font, wrapped line lists, configured line height, and spacing per line.
    """
    size = max(min_size, start_size)
    while size > min_size:
        font = load_font(font_path, size)
        line_h, line_step = compute_line_metrics(
            draw, font, line_spacing=line_spacing, tone_mark_scale=tone_mark_scale
        )
        lines = wrap_text_for_box(draw, text, font, max_width)
        total_h = line_h + (max(1, len(lines)) - 1) * line_step
        too_wide = any(
            text_size(draw, ln, font)[0] > max_width for ln in lines if ln
        )  # Does any single word exceed the max_width?

        if (
            lines and (not too_wide) and total_h <= max_height
        ):  # Does the accumulated height of all wrapped lines exceed the bubble's capacity?
            # We found a fitting size! Decrease it by 4 for a safety margin.
            final_size = max(min_size, size - 6)
            if final_size != size:
                font = load_font(font_path, final_size)
                line_h, line_step = compute_line_metrics(
                    draw,
                    font,
                    line_spacing=line_spacing,
                    tone_mark_scale=tone_mark_scale,
                )
                lines = wrap_text_for_box(draw, text, font, max_width)
            return font, lines, line_h, line_step
        size -= 1

    # Fallback to min_size
    font = load_font(font_path, min_size)
    line_h, line_step = compute_line_metrics(
        draw, font, line_spacing=line_spacing, tone_mark_scale=tone_mark_scale
    )
    lines = wrap_text_for_box(draw, text, font, max_width)
    return font, lines, line_h, line_step


def draw_scaled_text_line(image, position, text, font, fill="black", y_scale=1.0):
    """
    Draw one line of text with optional vertical scaling to compact glyph marks.

    Args:
        image (PIL.Image.Image): The image to draw on.
        position (tuple): The x, y position to draw the text.
        text (str): The text line to draw.
        font (PIL.ImageFont.FreeTypeFont): The font to use.
        fill (str): The color to draw the text.
        y_scale (float): The vertical scale.

    Returns:
        None
    """
    x, y = position
    if y_scale >= 0.99:
        ImageDraw.Draw(image).text((x, y), text, fill=fill, font=font)
        return

    # Draw on transparent layer first, then resize only text pixels (not full image).
    temp = Image.new("RGBA", image.size, (0, 0, 0, 0))
    temp_draw = ImageDraw.Draw(temp)
    temp_draw.text((x, y), text, fill=fill, font=font)
    box = temp_draw.textbbox((x, y), text, font=font)
    if not box:
        return

    crop = temp.crop(box)
    new_h = max(1, int(round(crop.height * max(0.5, y_scale))))
    if new_h != crop.height:
        # Bicubic keeps Thai marks smoother after vertical compression.
        crop = crop.resize((crop.width, new_h), Image.Resampling.BICUBIC)

    paste_x = box[0]
    paste_y = box[3] - new_h
    image.paste(crop, (paste_x, paste_y), crop)


def draw_ocr_boxes(image, ocr_blocks):
    """
    Draw OCR polygons (quad) or bbox fallback with index labels on an image.

    Args:
        image (PIL.Image.Image): The original PIL image.
        ocr_blocks (list): The list of dictionaries containing OCR bounding boxes/quad information.

    Returns:
        PIL.Image.Image: The image with annotated OCR boxes.
    """
    draw = ImageDraw.Draw(image)
    for idx, block in enumerate(ocr_blocks, start=1):
        quad = block.get("quad")
        box = block.get("bbox_2d")

        anchor_x = None
        anchor_y = None
        if quad and len(quad) == 8:
            points = [int(v) for v in quad]
            polygon = [
                (points[0], points[1]),
                (points[2], points[3]),
                (points[4], points[5]),
                (points[6], points[7]),
            ]
            draw.polygon(polygon, outline="red", width=4)
            anchor_x, anchor_y = polygon[0]
        elif box and len(box) == 4:
            x0, y0, x1, y1 = [int(v) for v in box]
            draw.rectangle([x0, y0, x1, y1], outline="red", width=3)
            anchor_x, anchor_y = x0, y0
        else:
            continue

        label = str(idx)
        font = load_font(DEFAULT_FONT_PATH, 30)
        label_box = draw.textbbox((anchor_x, max(0, anchor_y - 20)), label, font=font)
        draw.rectangle(label_box, fill="red")
        draw.text((anchor_x, max(0, anchor_y - 20)), label, fill="white", font=font)
    return image


def fill_boxes_with_white(image, ocr_blocks, padding=8, right_extra=0):
    """
    Fill OCR regions with white, using asymmetric padding around each box.

    Args:
        image (PIL.Image.Image): The original image.
        ocr_blocks (list): The list of dictionaries containing OCR bounding boxes.
        padding (int): The base padding to apply around the box.
        right_extra (int): The extra padding to apply on the right side.

    Returns:
        PIL.Image.Image: The image with white-filled OCR boxes.
    """
    draw = ImageDraw.Draw(image)
    w, h = image.size

    for block in ocr_blocks:
        box = block.get("bbox_2d")
        if not box or len(box) != 4:
            continue

        x0, y0, x1, y1 = [int(v) for v in box]
        # Keep top expansion smaller so we don't erase artwork above speech text.
        # top_padding = max(0, int(round(padding * TOP_PADDING_RATIO)))
        x0 = max(0, x0 - padding)
        y0 = max(0, y0 - padding)
        x1 = min(w - 1, x1 + padding + max(0, int(right_extra)))
        y1 = min(h - 1, y1 + padding + 3)

        if x1 > x0 and y1 > y0:
            draw.rectangle([x0, y0, x1, y1], fill="white")

    return image


def is_dark_box(image, box, threshold=70):
    """
    Return True if the mean luminance in the box is below a darkness threshold.

    Args:
        image (PIL.Image.Image): The original image.
        box (tuple): The x0, y0, x1, y1 bounding box.
        threshold (int): The darkness threshold luminance (0-255).

    Returns:
        bool: True if the specified box is darker than the threshold, False otherwise.
    """
    x0, y0, x1, y1 = box
    if x1 <= x0 or y1 <= y0:
        return False

    crop = image.crop((x0, y0, x1 + 1, y1 + 1)).convert(
        "L"
    )  # transforms this image segment into grayscale (Luminance mode)
    # Use average grayscale luminance to decide white-vs-black text rendering.
    mean_luma = ImageStat.Stat(crop).mean[0]
    return mean_luma < threshold


def print_debug_pairs(file_path, page_num, source_texts, translated_texts):
    """
    Print OCR and translation text pairs for per-page debugging.

    Args:
        file_path (str): The path to the file.
        page_num (int): The page number.
        source_texts (list): The list of original Japanese texts.
        translated_texts (list): The list of translated texts.

    Returns:
        None
    """
    print(f"[DEBUG] File={file_path} Page={page_num} OCR blocks={len(source_texts)}")
    for idx, (jp, th) in enumerate(zip(source_texts, translated_texts), start=1):
        print(f"[DEBUG]   #{idx} OCR: {jp}")
        print(f"[DEBUG]   #{idx} TH : {th}")


def draw_translated_text_in_boxes(
    image,
    ocr_blocks,
    translated_texts,
    font_path,
    padding=8,
    line_spacing=LINE_SPACING_PX,
    tone_mark_scale=TONE_MARK_VERTICAL_SCALE,
    top_margin=TOP_MARGIN_PX,
    right_padding_extra=RIGHT_PADDING_EXTRA_PX,
):
    """
    Render translated text into OCR boxes with adaptive colors and layout fitting.

    Args:
        image (PIL.Image.Image): The original PIL image.
        ocr_blocks (list): The list of dictionaries containing OCR bounding boxes.
        translated_texts (list): The list of translated text strings.
        font_path (str): The path to the font to use.
        padding (int): The base padding for text blocks.
        line_spacing (int): The vertical spacing between text lines.
        tone_mark_scale (float): The vertical scale adjustment for tone marks.
        top_margin (int): The top margin for the text.
        right_padding_extra (int): The additional right-side padding.

    Returns:
        PIL.Image.Image: The image with rendered translations.
    """
    debug_log("RENDER", f"Rendering translated text into {len(ocr_blocks)} box(es)")
    draw = ImageDraw.Draw(image)
    w, h = image.size
    source_for_color = image.copy()

    for block, translated in zip(ocr_blocks, translated_texts):
        box = block.get("bbox_2d")
        if not box or len(box) != 4:
            continue

        x0, y0, x1, y1 = [int(v) for v in box]
        # Match whitefill behavior: less top padding, extra right-side room.
        top_padding = max(0, int(round(padding * TOP_PADDING_RATIO)))
        x0 = max(0, x0 - padding)
        y0 = max(0, y0 - top_padding)
        x1 = min(w - 1, x1 + padding + max(0, int(right_padding_extra)))
        y1 = min(h - 1, y1 + padding + 3)

        if x1 <= x0 or y1 <= y0:
            continue

        box_w = x1 - x0
        box_h = y1 - y0

        # Fill the original (padded) box first to erase the Japanese text.
        dark_box = is_dark_box(source_for_color, (x0, y0, x1, y1))
        bg_fill = "black" if dark_box else "white"
        text_fill = "white" if dark_box else "black"
        draw.rectangle([x0, y0, x1, y1], fill=bg_fill)

        # Vertical Japanese text boxes are narrow columns where height is at
        # least 2× the width (e.g. a single stack of kanji ~25×150 px).
        # Normal speech bubbles have a ratio closer to 1:1, so a threshold of
        # 2.0 avoids widening ordinary bubbles that happen to be slightly tall.
        if box_w > 0 and (box_h / box_w) >= 3.5:
            cx = (x0 + x1) // 2
            half = max(box_w, box_h) // 4
            x0 = max(0, cx - half)
            x1 = min(w - 1, cx + half)
            box_w = x1 - x0
            # Redraw the full expanded box so both the newly added left and
            # right margins are filled with the same background colour.
            draw.rectangle([x0, y0, x1, y1], fill=bg_fill)

        # Seed the font-size search from the box height so large boxes get
        # large text and small boxes don't waste iterations shrinking from 72.
        start_size = max(14, int(box_h * 0.8))
        font, lines, line_h, line_step = fit_and_wrap_text(
            draw,
            translated,
            font_path,
            box_w,
            box_h,
            start_size=start_size,
            line_spacing=line_spacing,
            tone_mark_scale=tone_mark_scale,
        )

        if not lines:
            continue

        # Dividing by 2 is the standard mathematical trick for centering an object within an enclosed area.
        # Let's say your OCR bubble width (box_w) is 100 pixels.
        # The length of the text string width (line_w) is 60 pixels.
        # (100 - 60) = 40 pixels of empty, unused background space (space before the starts (0-39)).
        # If you don't divide by 2 and just draw at x = 40:

        # The text starts at 40 and extends 60 pixels.
        # The text goes from 40 to 100.
        # All 40 pixels of empty space are on the left side, pushing the text completely to the right edge.

        # If you divide by 2 ((100 - 60) // 2 = 20):
        # Your starting x coordinate becomes exactly 20.
        # The text starts at pixel 20 and extends 60 pixels to pixel 80.
        # This leaves exactly 20 pixels of empty space on the left side, and 20 pixels of empty space on the right side (100 - 80).
        # The text is now perfectly centered! 60 pixels of text are perfectly in the middle.

        # Calculate total height of the text block to center vertically, find empty space
        total_text_h = line_h + (len(lines) - 1) * line_step
        start_y = y0 + max(0, (box_h - total_text_h) // 2)

        y = start_y
        for line in lines:
            if y + line_h > y1 and y != start_y:
                break

            # Calculate width of the current line to center horizontally, find empty space
            line_w, _ = text_size(draw, line, font)
            line_x = x0 + max(0, (box_w - line_w) // 2)

            draw_scaled_text_line(
                image,
                (line_x, y),
                line,
                font=font,
                fill=text_fill,
                y_scale=tone_mark_scale,
            )
            y += line_step

    return image


def process_single_file(
    file_path,
    ocr_api_url,
    translation_api_url,
    output_dir,
    font_path,
    padding,
    ocr_connect_timeout,
    ocr_read_timeout,
    ocr_retries,
    ocr_jpeg_quality,
    progress_callback=None,
):
    """
    Run OCR, translation, rendering, and artifact export for one image/PDF file.

    Args:
        file_path (str): The path to the input file.
        ocr_api_url (str): The URL for the OCR API.
        translation_api_url (str): The URL for the translation API.
        output_dir (str): The directory to save processed outputs.
        font_path (str): The path to the font used for rendering.
        padding (int): The base padding for text blocks.
        ocr_connect_timeout (int): The timeout in seconds for OCR API connection.
        ocr_read_timeout (int): The timeout in seconds for reading OCR API response.
        ocr_retries (int): Number of retries for OCR requests.
        ocr_jpeg_quality (int): JPEG quality setting for image compression before OCR.
        progress_callback (callable, optional): A callback function for updating progress. Defaults to None.

    Returns:
        dict: A dictionary containing paths and statistics related to the processing including `pairs`, `json`, `images`, `analyzed_images`, `whitefill_images`, and `units`.
    """
    debug_log("PIPELINE", f"Start processing: {file_path}")
    is_pdf = file_path.lower().endswith(".pdf")

    output_images = []
    analyzed_images = []
    whitefill_images = []
    pairs = []

    if is_pdf:
        debug_log("PDF", f"Converting PDF to images: {file_path}")
        pages = convert_from_path(file_path, poppler_path=POPPLER_PATH)
        total_units = max(1, len(pages))
        if progress_callback:
            progress_callback("register", {"file": file_path, "units": total_units})

        for page_num, page_image in enumerate(pages, start=1):
            debug_log("PDF", f"Processing page {page_num}/{len(pages)}")
            img = page_image.convert("RGB")
            # OCR is done per-page image to avoid large monolithic PDF request stalls.
            ocr_response = run_ocr_for_pil_image(
                img,
                upload_name=f"{Path(file_path).name}_page_{page_num}",
                ocr_api_url=ocr_api_url,
                connect_timeout=ocr_connect_timeout,
                read_timeout=ocr_read_timeout,
                max_retries=ocr_retries,
                jpeg_quality=ocr_jpeg_quality,
            )
            page_result = (ocr_response.get("results") or [{}])[0]
            blocks = page_result.get("data", {}).get("ocr_blocks", [])
            valid_blocks = [b for b in blocks if (b.get("text") or "").strip()]
            source_texts = [(b.get("text") or "").strip() for b in valid_blocks]
            translated_texts = (
                run_translation(source_texts, translation_api_url)
                if source_texts
                else []
            )
            print_debug_pairs(file_path, page_num, source_texts, translated_texts)

            for jp, th in zip(source_texts, translated_texts):
                pairs.append({"file": file_path, "page": page_num, "jp": jp, "th": th})

            base_name = Path(file_path).stem

            analyzed = draw_ocr_boxes(img.copy(), valid_blocks)
            analyzed_name = f"{base_name}_page_{page_num}_analyzed.jpg"
            analyzed_path = os.path.join(output_dir, analyzed_name)
            analyzed.save(analyzed_path)
            analyzed_images.append(analyzed_path)
            debug_log("SAVE", f"Analyzed image saved: {analyzed_path}")

            whitefilled = fill_boxes_with_white(
                img.copy(),
                valid_blocks,
                padding=padding,
                right_extra=RIGHT_PADDING_EXTRA_PX,
            )
            white_name = f"{base_name}_page_{page_num}_whitefill.jpg"
            white_path = os.path.join(output_dir, white_name)
            whitefilled.save(white_path)
            whitefill_images.append(white_path)
            debug_log("SAVE", f"Whitefill image saved: {white_path}")

            rendered = draw_translated_text_in_boxes(
                img, valid_blocks, translated_texts, font_path, padding
            )
            out_name = f"{base_name}_page_{page_num}_translated.jpg"
            out_path = os.path.join(output_dir, out_name)
            rendered.save(out_path)
            output_images.append(out_path)
            debug_log("SAVE", f"Translated image saved: {out_path}")

            if progress_callback:
                progress_callback(
                    "advance", {"file": file_path, "units": 1, "page": page_num}
                )
    else:
        debug_log("IMAGE", f"Processing image file: {file_path}")
        total_units = 1
        if progress_callback:
            progress_callback("register", {"file": file_path, "units": total_units})

        with Image.open(file_path) as src_img:
            img = src_img.convert("RGB")
        ocr_response = run_ocr_for_pil_image(
            img,
            upload_name=Path(file_path).name,
            ocr_api_url=ocr_api_url,
            connect_timeout=ocr_connect_timeout,
            read_timeout=ocr_read_timeout,
            max_retries=ocr_retries,
            jpeg_quality=ocr_jpeg_quality,
        )
        page_result = (ocr_response.get("results") or [{}])[0]
        blocks = page_result.get("data", {}).get("ocr_blocks", [])
        valid_blocks = [b for b in blocks if (b.get("text") or "").strip()]
        source_texts = [(b.get("text") or "").strip() for b in valid_blocks]
        translated_texts = (
            run_translation(source_texts, translation_api_url) if source_texts else []
        )
        print_debug_pairs(file_path, 1, source_texts, translated_texts)

        for jp, th in zip(source_texts, translated_texts):
            pairs.append({"file": file_path, "page": 1, "jp": jp, "th": th})

        base_name = Path(file_path).stem

        analyzed = draw_ocr_boxes(img.copy(), valid_blocks)
        analyzed_name = f"{base_name}_analyzed.jpg"
        analyzed_path = os.path.join(output_dir, analyzed_name)
        analyzed.save(analyzed_path)
        analyzed_images.append(analyzed_path)
        debug_log("SAVE", f"Analyzed image saved: {analyzed_path}")

        whitefilled = fill_boxes_with_white(
            img.copy(),
            valid_blocks,
            padding=padding,
            right_extra=RIGHT_PADDING_EXTRA_PX,
        )
        white_name = f"{base_name}_whitefill.jpg"
        white_path = os.path.join(output_dir, white_name)
        whitefilled.save(white_path)
        whitefill_images.append(white_path)
        debug_log("SAVE", f"Whitefill image saved: {white_path}")

        rendered = draw_translated_text_in_boxes(
            img, valid_blocks, translated_texts, font_path, padding
        )
        out_name = f"{base_name}_translated.jpg"
        out_path = os.path.join(output_dir, out_name)
        rendered.save(out_path)
        output_images.append(out_path)
        debug_log("SAVE", f"Translated image saved: {out_path}")

        if progress_callback:
            progress_callback("advance", {"file": file_path, "units": 1, "page": 1})

    json_path = os.path.join(output_dir, f"{Path(file_path).stem}_jp_th.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(pairs, fh, ensure_ascii=False, indent=2)
    debug_log("SAVE", f"JSON saved: {json_path}")
    debug_log("PIPELINE", f"Finished processing: {file_path}")

    return {
        "pairs": pairs,
        "json": json_path,
        "images": output_images,
        "analyzed_images": analyzed_images,
        "whitefill_images": whitefill_images,
        "units": total_units,
    }


def save_uploaded_files(uploaded_files):
    """
    Persist Streamlit uploaded files to a temporary folder and return paths.

    Args:
        uploaded_files (list): The list of files uploaded through Streamlit.

    Returns:
        list: The list of temporary file paths where the files were saved.
    """
    temp_dir = tempfile.mkdtemp(prefix="manga_upload_")
    saved_paths = []

    for up in uploaded_files:
        out_path = os.path.join(temp_dir, up.name)
        with open(out_path, "wb") as fh:
            fh.write(up.getbuffer())
        saved_paths.append(out_path)

    return saved_paths


def main():
    """
    Build and run the Streamlit UI for the manga translation pipeline.

    Args:
        None

    Returns:
        None
    """
    st.set_page_config(page_title="Manga Translator UI", layout="wide")
    st.title("Manga Translator (OCR + Translation + Render)")

    with st.sidebar:
        st.header("Settings")
        api_input_mode = st.radio(
            "API input mode",
            ["Base URL + paths", "Full endpoint URLs"],
            horizontal=True,
        )

        if api_input_mode == "Base URL + paths":
            ocr_base_api_url = st.text_input(
                "OCR Base API URL", value="https://f4e4-34-11-36-230.ngrok-free.app"
            ).strip()
            translation_base_api_url = st.text_input(
                "Translation Base API URL",
                value="https://f1c4-34-63-163-234.ngrok-free.app",
            ).strip()
            ocr_api_path = st.text_input("OCR path", value="/predict").strip()
            translation_api_path = st.text_input(
                "Translation path", value="/translate"
            ).strip()

            if ocr_api_path and not ocr_api_path.startswith("/"):
                ocr_api_path = f"/{ocr_api_path}"
            if translation_api_path and not translation_api_path.startswith("/"):
                translation_api_path = f"/{translation_api_path}"

            ocr_api_url = f"{ocr_base_api_url.rstrip('/')}{ocr_api_path}"
            translation_api_url = (
                f"{translation_base_api_url.rstrip('/')}{translation_api_path}"
            )
            st.caption(f"OCR endpoint: {ocr_api_url}")
            st.caption(f"Translation endpoint: {translation_api_url}")
        else:
            ocr_api_url = st.text_input(
                "OCR API URL", value="https://c9e7-34-41-56-70.ngrok-free.app/predict"
            )
            translation_api_url = st.text_input(
                "Translation API URL",
                value="https://7f4d-35-231-188-217.ngrok-free.app/translate",
            )
        font_path = st.text_input("Layijimahaniyom Font Path", value=DEFAULT_FONT_PATH)
        padding = st.number_input(
            "Box Padding", min_value=0, max_value=50, value=8, step=1
        )
        ocr_connect_timeout = st.number_input(
            "OCR Connect Timeout (s)", min_value=5, max_value=120, value=30, step=1
        )
        ocr_read_timeout = st.number_input(
            "OCR Read Timeout (s)", min_value=30, max_value=1800, value=300, step=30
        )
        ocr_retries = st.number_input(
            "OCR Retries", min_value=0, max_value=5, value=2, step=1
        )
        ocr_jpeg_quality = st.number_input(
            "OCR JPEG Quality", min_value=50, max_value=100, value=95, step=1
        )
        output_dir = st.text_input("Output Directory", value="output_results")
        st.caption(
            "For PDF support, install Poppler and ensure it is available on PATH."
        )

    mode = st.radio(
        "Choose input source", ["Upload files", "Use existing files"], horizontal=True
    )
    selected_paths = []

    if mode == "Upload files":
        uploaded = st.file_uploader(
            "Upload image/PDF files",
            type=["png", "jpg", "jpeg", "pdf"],
            accept_multiple_files=True,
        )
        if uploaded:
            selected_paths = save_uploaded_files(uploaded)
            st.success(f"Loaded {len(selected_paths)} uploaded file(s).")
    else:
        default_dir = "images"
        base_dir = st.text_input("Existing files directory", value=default_dir)
        existing = []
        if os.path.isdir(base_dir):
            existing = [
                os.path.join(base_dir, name)
                for name in sorted(os.listdir(base_dir))
                if os.path.splitext(name)[1].lower() in ALLOWED_EXT
                and os.path.isfile(os.path.join(base_dir, name))
            ]

        picked = st.multiselect(
            "Select existing files", options=existing, default=existing
        )

        extra_patterns = st.text_area(
            "Optional extra paths/globs (one per line)",
            value="",
            placeholder="images/*.png\nimages/sample.pdf",
        )

        selected_paths.extend(picked)
        if extra_patterns.strip():
            selected_paths.extend(collect_input_files(extra_patterns.splitlines()))

        selected_paths = list(dict.fromkeys(selected_paths))
        if selected_paths:
            st.info(f"Selected {len(selected_paths)} existing file(s).")

    if st.button("Run Translation Pipeline", type="primary"):
        debug_log("UI", "Run Translation Pipeline clicked")
        if not selected_paths:
            st.error("Please upload files or select existing files first.")
            return

        if not ocr_api_url.strip() or not translation_api_url.strip():
            st.error("Please provide both OCR and Translation API URLs.")
            return

        os.makedirs(output_dir, exist_ok=True)
        all_pairs = []
        all_images = []
        all_analyzed_images = []
        all_whitefill_images = []
        all_jsons = []

        progress = st.progress(0)
        status = st.empty()
        known_units = 0
        completed_units = 0

        def progress_callback(event, payload):
            """Update status text and progress bar from per-file/page progress events."""
            nonlocal known_units, completed_units
            if event == "register":
                known_units += max(1, int(payload.get("units", 1)))
                status.write(f"Queued: {Path(payload.get('file', '')).name}")
            elif event == "advance":
                completed_units += max(1, int(payload.get("units", 1)))
                file_name = Path(payload.get("file", "")).name
                page = payload.get("page", "?")
                status.write(
                    f"Processing page {page} | {file_name} | {completed_units}/{max(known_units, 1)}"
                )

            # Handles unknown totals early, then converges as units are registered.
            denominator = max(known_units, completed_units, 1)
            progress.progress(min(1.0, completed_units / denominator))

        for idx, path in enumerate(selected_paths, start=1):
            debug_log("UI", f"File {idx}/{len(selected_paths)}: {path}")
            status.write(f"Processing ({idx}/{len(selected_paths)}): {path}")
            try:
                result = process_single_file(
                    file_path=path,
                    ocr_api_url=ocr_api_url,
                    translation_api_url=translation_api_url,
                    output_dir=output_dir,
                    font_path=font_path,
                    padding=int(padding),
                    ocr_connect_timeout=int(ocr_connect_timeout),
                    ocr_read_timeout=int(ocr_read_timeout),
                    ocr_retries=int(ocr_retries),
                    ocr_jpeg_quality=int(ocr_jpeg_quality),
                    progress_callback=progress_callback,
                )
                all_pairs.extend(result["pairs"])
                all_images.extend(result["images"])
                all_analyzed_images.extend(result["analyzed_images"])
                all_whitefill_images.extend(result["whitefill_images"])
                all_jsons.append(result["json"])
            except Exception as exc:
                debug_log("ERROR", f"Failed for {path}: {exc}")
                st.error(f"Failed for {path}: {exc}")

        progress.progress(1.0)

        combined_path = os.path.join(output_dir, "all_files_jp_th.json")
        with open(combined_path, "w", encoding="utf-8") as fh:
            json.dump(all_pairs, fh, ensure_ascii=False, indent=2)

        st.success(f"Done. Processed {len(selected_paths)} file(s).")
        debug_log("UI", f"Pipeline completed for {len(selected_paths)} file(s)")

        st.subheader("Output Files")
        st.write(f"Combined JSON: {combined_path}")

        with open(combined_path, "rb") as fh:
            st.download_button(
                "Download combined JSON",
                data=fh.read(),
                file_name="all_files_jp_th.json",
                mime="application/json",
            )

        if all_jsons:
            st.write("Per-file JSON:")
            for p in all_jsons:
                with open(p, "rb") as fh:
                    st.download_button(
                        label=f"Download {Path(p).name}",
                        data=fh.read(),
                        file_name=Path(p).name,
                        mime="application/json",
                        key=f"dl_{p}",
                    )

        if all_images:
            st.subheader("Rendered Images")
            preview_count = min(10, len(all_images))
            for p in all_images[:preview_count]:
                st.image(p, caption=Path(p).name, width="stretch")
            if len(all_images) > preview_count:
                st.caption(
                    f"Showing first {preview_count} of {len(all_images)} rendered images."
                )

        if all_analyzed_images:
            st.subheader("Analyzed OCR Box Images")
            st.write(f"Saved {len(all_analyzed_images)} analyzed image(s).")

        if all_whitefill_images:
            st.subheader("Whitefill Images")
            st.write(f"Saved {len(all_whitefill_images)} whitefill image(s).")


if __name__ == "__main__":
    if is_streamlit_run_context():
        main()
    else:
        print(
            "This app must be run with Streamlit.\n"
            "Use: streamlit run streamlit_app.py"
        )
