# Function Reference: streamlit_app.py

This document provides a summary of every function in `streamlit_app.py`, including:
- Short description
- Detailed description
- What is it used for?
- Why use this?
- Who calls the function?

---

## 1. `debug_log(stage, message)`
**Short Description:**
Prints a debug message tagged by pipeline stage.

**Code Snippet:**
```python
def debug_log(stage, message):  # Define a function that takes a stage label and a message
	print(f"[DEBUG][{stage}] {message}")  # Print the message with a [DEBUG] tag and the stage label
```

**Detailed Description:**
Uses Python's built-in print function to output a formatted debug message. The function is called by other pipeline functions to provide stage-specific logs, aiding in debugging and tracing the flow of execution.

**Used For:**
Debugging and tracing execution flow.

**Why Use:**
Helps developers understand what part of the pipeline is running and diagnose issues.

**Who Calls:**
Various functions throughout the pipeline for logging.

---

## 2. `is_streamlit_run_context()`
**Short Description:**
Detects if code is running inside a Streamlit script context.

**Code Snippet:**
```python
def is_streamlit_run_context():  # Define a function to check if running in Streamlit
	try:
		from streamlit.runtime.scriptrunner import get_script_run_ctx  # Import the Streamlit context checker
		return get_script_run_ctx() is not None  # Return True if Streamlit context exists
	except Exception:  # If import or call fails
		return False  # Not running in Streamlit
```

**Detailed Description:**
Imports and calls `get_script_run_ctx` from `streamlit.runtime.scriptrunner` to check if the code is running inside a Streamlit execution context. Returns True if Streamlit is running, otherwise False. Used to conditionally execute code only in the correct environment.

**Used For:**
Conditional logic depending on whether the app is run via Streamlit.

**Why Use:**
Prevents code from running outside Streamlit or enables alternate behavior.

**Who Calls:**
Main block at the end of the file.

---

## 3. `collect_input_files(inputs)`
**Short Description:**
Collects valid image/PDF files from paths, folders, or glob patterns.

**Code Snippet:**
```python
def collect_input_files(inputs):  # Collect files from a list of paths, folders, or patterns
	debug_log("INPUT", f"Collecting files from {len(inputs)} input item(s)")  # Log the number of input items
	collected = []  # Initialize the list to store collected file paths
	for item in inputs:  # Iterate over each input
		item = item.strip()  # Remove leading/trailing whitespace
		if not item:  # Skip empty strings
			continue
		if os.path.isdir(item):  # If the item is a directory
			for name in sorted(os.listdir(item)):  # List and sort files in the directory
				path = os.path.join(item, name)  # Build the full path
				ext = os.path.splitext(path)[1].lower()  # Get the file extension
				if os.path.isfile(path) and ext in ALLOWED_EXT:  # Check if file and allowed extension
					collected.append(path)  # Add to collected list
		elif any(ch in item for ch in ["*", "?", "["]):  # If the item is a glob pattern
			for path in sorted(glob.glob(item)):  # Expand the glob and sort
				ext = os.path.splitext(path)[1].lower()  # Get the file extension
				if os.path.isfile(path) and ext in ALLOWED_EXT:  # Check if file and allowed extension
					collected.append(path)  # Add to collected list
		elif os.path.isfile(item):  # If the item is a file
			ext = os.path.splitext(item)[1].lower()  # Get the file extension
			if ext in ALLOWED_EXT:  # Check if allowed extension
				collected.append(item)  # Add to collected list
	return list(dict.fromkeys(collected))  # Remove duplicates and return the list
```

**Detailed Description:**
Uses `os.path.isdir`, `os.listdir`, `os.path.isfile`, and `glob.glob` to collect files from directories, explicit paths, or glob patterns. Filters files by allowed extensions. Removes duplicates using `dict.fromkeys`. Calls `debug_log` for traceability.

**Used For:**
Gathering input files for processing.

**Why Use:**
Supports flexible user input (single files, folders, wildcards).

**Who Calls:**
Streamlit UI logic when user selects files or enters patterns.

---

## 4. `run_ocr(file_path, ocr_api_url)`
**Short Description:**
Uploads a file to the OCR API and returns parsed JSON.

**Code Snippet:**
```python
def run_ocr(file_path, ocr_api_url):  # Upload a file to the OCR API and return the parsed JSON
	debug_log("OCR", f"Uploading file path: {file_path}")  # Log the file being uploaded
	lower = file_path.lower()  # Convert file path to lowercase for extension check
	if lower.endswith(".pdf"):  # If file is a PDF
		mime_type = "application/pdf"  # Set MIME type for PDF
	elif lower.endswith(".png"):  # If file is a PNG
		mime_type = "image/png"  # Set MIME type for PNG
	else:  # Otherwise assume JPEG
		mime_type = "image/jpeg"  # Set MIME type for JPEG
	headers = {"ngrok-skip-browser-warning": "true"}  # Set custom header for ngrok
	with open(file_path, "rb") as fh:  # Open the file in binary mode
		files = {"file": (os.path.basename(file_path), fh, mime_type)}  # Prepare file upload payload
		response = requests.post(ocr_api_url, files=files, headers=headers, timeout=300)  # Send POST request
	response.raise_for_status()  # Raise error if HTTP request failed
	data = response.json()  # Parse JSON response
	if data.get("status") != "success":  # Check if OCR API returned success
		raise ValueError(f"OCR server returned non-success response: {data}")  # Raise error if not
	return data  # Return the parsed data
```

**Detailed Description:**
Opens the file in binary mode and sends it to the OCR API using `requests.post`. Sets the correct MIME type based on file extension. Checks the HTTP response with `raise_for_status`, parses the JSON with `response.json`, and validates the status. Calls `debug_log` for logging.

**Used For:**
Performing OCR on input files.

**Why Use:**
Automates OCR step in the pipeline.

**Who Calls:**
`process_single_file()`

---

## 5. `run_ocr_for_pil_image(image, upload_name, ocr_api_url, ...)`
**Short Description:**
Uploads a PIL image to the OCR API with retries and timeout controls.

**Code Snippet:**
```python
def run_ocr_for_pil_image(
	image,
	upload_name,
	ocr_api_url,
	connect_timeout=DEFAULT_OCR_CONNECT_TIMEOUT_SEC,
	read_timeout=DEFAULT_OCR_READ_TIMEOUT_SEC,
	max_retries=DEFAULT_OCR_RETRIES,
	jpeg_quality=DEFAULT_OCR_JPEG_QUALITY,
):
	debug_log("OCR", f"Uploading in-memory image: {upload_name}")
	headers = {"ngrok-skip-browser-warning": "true", "Connection": "close"}
	buffer = io.BytesIO()
	image.save(buffer, format="JPEG", quality=int(jpeg_quality))
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
```

**Detailed Description:**
Converts a PIL image to JPEG bytes using `image.save` and `io.BytesIO`. Uploads the image to the OCR API with `requests.post`, handling connection/read timeouts and retry logic. Uses `time.sleep` for backoff. Parses and validates the JSON response. Calls `debug_log` for each attempt and error.

**Used For:**
OCR on in-memory images (e.g., PDF pages converted to images).

**Why Use:**
Improves reliability of OCR requests, especially for large or slow files.

**Who Calls:**
`process_single_file()`

---

## 6. `run_translation(sentences, translation_api_url)`
**Short Description:**
Translates Japanese sentences via the translation API.

**Code Snippet:**
```python
def run_translation(sentences, translation_api_url):
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
```

**Detailed Description:**
Iterates over the list of sentences, sending each as a JSON payload to the translation API using `requests.post`. Parses the JSON response and collects the translated text. Uses `debug_log` for progress logging.

**Used For:**
Automating translation of OCR results.

**Why Use:**
Batch translation of text for efficiency and consistency.

**Who Calls:**
`process_single_file()`

---

## 7. `load_font(font_path, size)`
**Short Description:**
Loads a TrueType font or falls back to PIL default.

**Code Snippet:**
```python
def load_font(font_path, size):
	try:
		return ImageFont.truetype(font_path, size)
	except OSError:
		return ImageFont.load_default()
```

**Detailed Description:**
Uses `ImageFont.truetype` from PIL to load a TrueType font. If the font file is not found or invalid, falls back to `ImageFont.load_default` to ensure text rendering does not fail.

**Used For:**
Rendering text on images.

**Why Use:**
Ensures text rendering works even if custom font is missing.

**Who Calls:**
Rendering functions like `draw_ocr_boxes`, `draw_translated_text_in_boxes`, etc.

---

## 8. `text_size(draw, text, font)`
**Short Description:**
Measures rendered text width and height.

**Code Snippet:**
```python
def text_size(draw, text, font):
	box = draw.textbbox((0, 0), text, font=font)
	return box[2] - box[0], box[3] - box[1]
```

**Detailed Description:**
Calls `draw.textbbox` from PIL to get the bounding box of the rendered text, then computes width and height. Used for precise text layout and fitting.

**Used For:**
Text layout and fitting in boxes.

**Why Use:**
Ensures text fits within designated regions.

**Who Calls:**
Text wrapping and fitting functions.

---

## 9. `compute_line_metrics(draw, font, line_spacing=0, tone_mark_scale=1.0)`
**Short Description:**
Computes line height and step for text rendering.

**Code Snippet:**
```python
def compute_line_metrics(draw, font, line_spacing=0, tone_mark_scale=1.0):
	_, base_line_h = text_size(draw, "Ag", font)
	base_line_h = max(1, base_line_h)
	rendered_line_h = max(1, int(round(base_line_h * max(0.5, tone_mark_scale))))
	line_step = rendered_line_h + max(0, int(line_spacing))
	return rendered_line_h, max(1, line_step)
```

**Detailed Description:**
Calls `text_size` to measure a sample string, then applies scaling for tone marks and adds line spacing. Returns the line height and the vertical step for multi-line text rendering.

**Used For:**
Multi-line text rendering.

**Why Use:**
Controls vertical spacing for readable text.

**Who Calls:**
Text fitting and rendering functions.

---

## 10. `wrap_text_for_box(draw, text, font, max_width)`
**Short Description:**
Wraps Thai text at word boundaries for a given box width.

**Code Snippet:**
```python
def wrap_text_for_box(draw, text, font, max_width):
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
```

**Detailed Description:**
Uses `pythainlp.word_tokenize` (if installed) to split Thai text into words for natural line breaks. Falls back to whitespace splitting if unavailable. Uses `font.getlength` to measure line width and wraps text to fit within `max_width`.

**Used For:**
Natural line breaking for Thai text.

**Why Use:**
Improves readability of rendered translations.

**Who Calls:**
Text fitting functions.

---

## 11. `fit_and_wrap_text(...)`
**Short Description:**
Finds a fitting font size and wraps lines for a text box.

**Code Snippet:**
```python
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
		)
		if (
			lines and (not too_wide) and total_h <= max_height
		):
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
	font = load_font(font_path, min_size)
	line_h, line_step = compute_line_metrics(
		draw, font, line_spacing=line_spacing, tone_mark_scale=tone_mark_scale
	)
	lines = wrap_text_for_box(draw, text, font, max_width)
	return font, lines, line_h, line_step
```

**Detailed Description:**
Calls `load_font`, `compute_line_metrics`, and `wrap_text_for_box` in a loop, reducing font size until the text fits within the given box dimensions. Ensures no line exceeds the box width and the total height fits. Returns the font, wrapped lines, and metrics.

**Used For:**
Adaptive text rendering in speech bubbles.

**Why Use:**
Ensures translated text fits and is readable.

**Who Calls:**
`draw_translated_text_in_boxes()`

---

## 12. `draw_scaled_text_line(image, position, text, font, fill="black", y_scale=1.0)`
**Short Description:**
Draws a line of text with optional vertical scaling.

**Code Snippet:**
```python
def draw_scaled_text_line(image, position, text, font, fill="black", y_scale=1.0):
	x, y = position
	if y_scale >= 0.99:
		ImageDraw.Draw(image).text((x, y), text, fill=fill, font=font)
		return
	temp = Image.new("RGBA", image.size, (0, 0, 0, 0))
	temp_draw = ImageDraw.Draw(temp)
	temp_draw.text((x, y), text, fill=fill, font=font)
	box = temp_draw.textbbox((x, y), text, font=font)
	if not box:
		return
	crop = temp.crop(box)
	new_h = max(1, int(round(crop.height * max(0.5, y_scale))))
	if new_h != crop.height:
		crop = crop.resize((crop.width, new_h), Image.Resampling.BICUBIC)
	paste_x = box[0]
	paste_y = box[3] - new_h
	image.paste(crop, (paste_x, paste_y), crop)
```

**Detailed Description:**
Uses PIL's `ImageDraw.text` to render text. If vertical scaling is needed, draws text on a transparent layer, crops, and resizes it with `Image.Resampling.BICUBIC` before pasting onto the image. This preserves Thai tone marks and improves appearance.

**Used For:**
Rendering Thai text with proper mark placement.

**Why Use:**
Improves appearance of Thai text in speech bubbles.

**Who Calls:**
`draw_translated_text_in_boxes()`

---

## 13. `draw_ocr_boxes(image, ocr_blocks)`
**Short Description:**
Draws OCR polygons or bounding boxes with index labels.

**Code Snippet:**
```python
def draw_ocr_boxes(image, ocr_blocks):
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
```

**Detailed Description:**
Draws polygons or rectangles on the image using `ImageDraw.polygon` or `ImageDraw.rectangle` for each OCR block. Labels each region with an index using `draw.text`. Calls `load_font` for label rendering. Used for visual debugging of OCR output.

**Used For:**
Visualizing OCR results.

**Why Use:**
Helps verify OCR accuracy and region detection.

**Who Calls:**
`process_single_file()`

---

## 14. `fill_boxes_with_white(image, ocr_blocks, padding=8, right_extra=0)`
**Short Description:**
Fills OCR regions with white color.

**Code Snippet:**
```python
def fill_boxes_with_white(image, ocr_blocks, padding=8, right_extra=0):
	draw = ImageDraw.Draw(image)
	w, h = image.size
	for block in ocr_blocks:
		box = block.get("bbox_2d")
		if not box or len(box) != 4:
			continue
		x0, y0, x1, y1 = [int(v) for v in box]
		x0 = max(0, x0 - padding)
		y0 = max(0, y0 - padding)
		x1 = min(w - 1, x1 + padding + max(0, int(right_extra)))
		y1 = min(h - 1, y1 + padding + 3)
		if x1 > x0 and y1 > y0:
			draw.rectangle([x0, y0, x1, y1], fill="white")
	return image
```

**Detailed Description:**
For each OCR block, calculates a padded rectangle and fills it with white using `ImageDraw.rectangle`. Ensures the original Japanese text/artwork is erased before rendering the translation.

**Used For:**
Preparing image for translated text overlay.

**Why Use:**
Removes Japanese text before rendering translation.

**Who Calls:**
`process_single_file()`

---

## 15. `is_dark_box(image, box, threshold=70)`
**Short Description:**
Checks if a region is dark based on mean luminance.

**Code Snippet:**
```python
def is_dark_box(image, box, threshold=70):
	x0, y0, x1, y1 = box
	if x1 <= x0 or y1 <= y0:
		return False
	crop = image.crop((x0, y0, x1 + 1, y1 + 1)).convert("L")
	mean_luma = ImageStat.Stat(crop).mean[0]
	return mean_luma < threshold
```

**Detailed Description:**
Crops the image to the given box, converts to grayscale with `.convert('L')`, and computes the mean luminance using `ImageStat.Stat`. Compares to a threshold to decide if the region is dark (for adaptive text color).

**Used For:**
Adaptive text color selection.

**Why Use:**
Ensures text is readable regardless of background.

**Who Calls:**
`draw_translated_text_in_boxes()`

---

## 16. `print_debug_pairs(file_path, page_num, source_texts, translated_texts)`
**Short Description:**
Prints OCR and translation text pairs for debugging.

**Code Snippet:**
```python
def print_debug_pairs(file_path, page_num, source_texts, translated_texts):
	print(f"[DEBUG] File={file_path} Page={page_num} OCR blocks={len(source_texts)}")
	for idx, (jp, th) in enumerate(zip(source_texts, translated_texts), start=1):
		print(f"[DEBUG]   #{idx} OCR: {jp}")
		print(f"[DEBUG]   #{idx} TH : {th}")
```

**Detailed Description:**
Uses Python's print function to output the original (OCR) and translated text pairs for each block on a page. Helps with debugging and verifying translation results.

**Used For:**
Debugging translation accuracy.

**Why Use:**
Helps developers verify translation output.

**Who Calls:**
`process_single_file()`

---

## 17. `draw_translated_text_in_boxes(...)`
**Short Description:**
Renders translated text into OCR boxes with adaptive layout and color.

**Code Snippet:**
```python
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
	debug_log("RENDER", f"Rendering translated text into {len(ocr_blocks)} box(es)")
	draw = ImageDraw.Draw(image)
	w, h = image.size
	source_for_color = image.copy()
	for block, translated in zip(ocr_blocks, translated_texts):
		box = block.get("bbox_2d")
		if not box or len(box) != 4:
			continue
		x0, y0, x1, y1 = [int(v) for v in box]
		top_padding = max(0, int(round(padding * TOP_PADDING_RATIO)))
		x0 = max(0, x0 - padding)
		y0 = max(0, y0 - top_padding)
		x1 = min(w - 1, x1 + padding + max(0, int(right_padding_extra)))
		y1 = min(h - 1, y1 + padding + 3)
		if x1 <= x0 or y1 <= y0:
			continue
		box_w = x1 - x0
		box_h = y1 - y0
		dark_box = is_dark_box(source_for_color, (x0, y0, x1, y1))
		bg_fill = "black" if dark_box else "white"
		text_fill = "white" if dark_box else "black"
		draw.rectangle([x0, y0, x1, y1], fill=bg_fill)
		if box_w > 0 and (box_h / box_w) >= 3.5:
			cx = (x0 + x1) // 2
			half = max(box_w, box_h) // 4
			x0 = max(0, cx - half)
			x1 = min(w - 1, cx + half)
			box_w = x1 - x0
			draw.rectangle([x0, y0, x1, y1], fill=bg_fill)
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
		total_text_h = line_h + (len(lines) - 1) * line_step
		start_y = y0 + max(0, (box_h - total_text_h) // 2)
		y = start_y
		for line in lines:
			if y + line_h > y1 and y != start_y:
				break
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
```

**Detailed Description:**
For each OCR block, calculates the padded box, determines background color with `is_dark_box`, fills the region, and fits/wraps the translated text using `fit_and_wrap_text`. Draws each line with `draw_scaled_text_line`, centering text horizontally and vertically. Handles vertical/narrow boxes for Japanese text.

**Used For:**
Overlaying translations onto manga images.

**Why Use:**
Automates the rendering of translated speech bubbles.

**Who Calls:**
`process_single_file()`

---

## 18. `process_single_file(...)`
**Short Description:**
Runs OCR, translation, rendering, and export for one file.

**Code Snippet:**
```python
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
				progress_callback("advance", {"file": file_path, "units": 1, "page": page_num})
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
```

**Detailed Description:**
Coordinates the entire pipeline for one file. For PDFs, uses `convert_from_path` to split into images. Calls `run_ocr_for_pil_image` for OCR, `run_translation` for translation, and rendering functions (`draw_ocr_boxes`, `fill_boxes_with_white`, `draw_translated_text_in_boxes`) for visualization. Saves outputs with PIL and writes results to JSON. Handles progress updates via callback.

**Used For:**
Processing each input file end-to-end.

**Why Use:**
Centralizes the main pipeline logic for modularity and reuse.

**Who Calls:**
Streamlit UI logic (main app loop).

---

## 19. `save_uploaded_files(uploaded_files)`
**Short Description:**
Saves Streamlit-uploaded files to a temp folder.

**Code Snippet:**
```python
def save_uploaded_files(uploaded_files):
	temp_dir = tempfile.mkdtemp(prefix="manga_upload_")
	saved_paths = []
	for up in uploaded_files:
		out_path = os.path.join(temp_dir, up.name)
		with open(out_path, "wb") as fh:
			fh.write(up.getbuffer())
		saved_paths.append(out_path)
	return saved_paths
```

**Detailed Description:**
Uses `tempfile.mkdtemp` to create a temporary directory. Iterates over Streamlit-uploaded files, writing their contents to disk with `open(..., 'wb')` and `up.getbuffer()`. Returns the list of saved file paths.

**Used For:**
Handling user uploads in the web UI.

**Why Use:**
Bridges Streamlit's upload mechanism with file-based processing.

**Who Calls:**
Streamlit UI logic.

---

## 20. `main()`
**Short Description:**
Builds and runs the Streamlit UI for the manga translation pipeline.

**Code Snippet:**
```python
def main():
	st.set_page_config(page_title="Manga Translator UI", layout="wide")
	st.title("Manga Translator (OCR + Translation + Render)")
	# ... UI and pipeline orchestration code ...
```

**Detailed Description:**
Uses Streamlit UI components (`st.set_page_config`, `st.title`, `st.sidebar`, etc.) to build the web interface. Handles user input for API URLs, file selection, and parameters. Calls `process_single_file` for each selected file and displays results, progress, and download buttons. Orchestrates the entire user workflow.

**Used For:**
User interaction and pipeline orchestration.

**Why Use:**
Provides a user-friendly interface for the translation workflow.

**Who Calls:**
Streamlit runtime (when the script is run as main).

---
