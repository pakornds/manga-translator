import os # Import the os module for interacting with the operating system (e.g., file paths)
import glob # Import glob to search for files that match a specific pattern
import json # Import json to parse and create JSON formatted data
import io # Import io to handle byte streams (images in memory instead of on disk)
import time # Import time to handle delays and timeouts during API retries
import csv # Import csv to read and write comma-separated values files for our reports
from pathlib import Path # Import Path from pathlib for an object-oriented way to handle file paths

import requests # Import requests to make HTTP POST/GET calls to your OCR and Translation APIs
import numpy as np # Import numpy for high-performance matrix and array operations (used for pixel masking)
from PIL import Image, ImageDraw, ImageFont, ImageStat, ImageFilter # Import Pillow modules for image manipulation, drawing, fonts, stats, and filters
from pdf2image import convert_from_path # Import convert_from_path to extract images from PDF files

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".pdf"} # Define a set of allowed file extensions that the script will process
DEFAULT_FONT_PATH = r"C:\Users\pakor\AppData\Local\Microsoft\Windows\Fonts\LayijiMahaniyomV1.ttf" # Set the default path to the Thai font used for rendering
POPPLER_PATH = r"C:\poppler-25.12.0\Library\bin" # Set the path to the Poppler binaries, required for reading PDFs

TONE_MARK_VERTICAL_SCALE = 0.65 # Set the vertical scaling factor for text to compress Thai tone marks and save space
LINE_SPACING_PX = 4 # Set the number of pixels to leave empty between lines of wrapped text
TOP_MARGIN_PX = 20 # Set a default top margin in pixels (unused in the dynamic calculation but kept for reference)
RIGHT_PADDING_EXTRA_PX = 10 # Set extra padding on the right side of the bubble to ensure text doesn't touch the border
TOP_PADDING_RATIO = 0.5 # Set the ratio of top padding relative to base padding to avoid drawing over character hair/faces
DEFAULT_OCR_CONNECT_TIMEOUT_SEC = 20 # Set the maximum time in seconds to wait for the OCR server to accept the connection
DEFAULT_OCR_READ_TIMEOUT_SEC = 300 # Set the maximum time in seconds to wait for the OCR server to finish processing and return data
DEFAULT_OCR_RETRIES = 2 # Set the maximum number of times to retry an OCR request if it fails
DEFAULT_OCR_JPEG_QUALITY = 95 # Set the JPEG compression quality (0-100) used when sending images to the OCR API

def debug_log(stage, message): # Define a helper function to print formatted debug messages
    print(f"[DEBUG][{stage}] {message}") # Print the debug message with the stage tag for easy tracking in the console

def collect_input_files(input_dir): # Define a function to recursively find all valid image/pdf files in a directory
    collected = [] # Initialize an empty list to store the file paths we find
    for root, _, files in os.walk(input_dir[0]): # Walk through the directory tree (assuming input_dir is a list with one directory)
        for file in files: # Loop through every file found in the current folder
            ext = os.path.splitext(file)[1].lower() # Extract the file extension and convert it to lowercase
            if ext in ALLOWED_EXT: # Check if the extension is in our allowed list (.png, .jpg, etc.)
                collected.append(os.path.join(root, file)) # If it is allowed, join the root path and filename and add it to our list
    return sorted(list(dict.fromkeys(collected))) # Remove duplicates by converting to a dict, then back to a list, sort it, and return it

# --------------------------------------------------------- # A visual separator for the code sections
# METRIC EVALUATION LOGIC # Section header for the new layout metrics
# --------------------------------------------------------- # A visual separator for the code sections
def compute_layout_metrics(original_img, text_mask_img, original_box): # Define the function to calculate layout metrics
    """ # Start of a docstring to document the function
    Computes Overflow, Overlap, and Whitespace metrics for a single rendered text bubble. # Description of the function
    """ # End of the docstring
    # 1. Setup boolean mask of where the text actually rendered # Comment explaining the next step
    text_mask = np.array(text_mask_img) > 0 # Convert the grayscale text mask image into a boolean numpy array (True where text exists)
    total_text_pixels = np.sum(text_mask) # Count the total number of True pixels (i.e., total text footprint)

    # If no text was drawn, return fallback/worst-case metrics # Comment explaining the edge case
    if total_text_pixels == 0: # Check if no text pixels were generated
        return 0.0, 0.0, 1.0 # Return 0 overflow, 0 overlap, and 100% whitespace if empty

    w, h = original_img.size # Get the width and height of the original image
    x0, y0, x1, y1 = [int(v) for v in original_box] # Extract and convert the bounding box coordinates to integers
    bx0, by0 = max(0, x0), max(0, y0) # Ensure the left and top coordinates are not negative (off-screen)
    bx1, by1 = min(w, x1), min(h, y1) # Ensure the right and bottom coordinates don't exceed the image dimensions

    # 2. OVERFLOW RATE: Text pixels outside the original, unpadded detection box # Comment explaining Overflow metric
    bubble_mask = np.zeros((h, w), dtype=bool) # Create a blank boolean canvas the size of the whole image (all False)
    bubble_mask[by0:by1, bx0:bx1] = True # Set the pixels inside the original bounding box to True
    
    overflow_mask = text_mask & ~bubble_mask # Find pixels where there IS text AND it is NOT inside the original bubble
    overflow_rate = np.sum(overflow_mask) / total_text_pixels # Calculate the percentage of text that spilled outside the box

    # 3. OVERLAP RATE: Text inappropriately intersecting with drawing lines # Comment explaining Overlap metric
    # We use a standard edge detection filter to find high-variance pixels in the original artwork # Comment explaining methodology
    gray = original_img.convert("L") # Convert the original clean manga image into grayscale
    edges = gray.filter(ImageFilter.FIND_EDGES) # Apply Pillow's edge detection filter to highlight line art
    edge_arr = np.array(edges) # Convert the edge-detected image into a numpy array for math operations
    
    # Threshold 50 isolates harsh drawing lines / high-variance background # Comment explaining the threshold
    edge_mask = edge_arr > 50  # Create a boolean mask where True represents a strong, harsh line in the drawing
    overlap_mask = text_mask & edge_mask # Find pixels where there IS text AND there IS a harsh drawing line underneath
    overlap_rate = np.sum(overlap_mask) / total_text_pixels # Calculate the percentage of text drawn over line art

    # 4. WHITESPACE RATIO: How much of the bubble is left completely empty # Comment explaining Whitespace metric
    # Calculate the actual footprint (bounding box) of all the text combined # Comment explaining the sub-step
    rows = np.any(text_mask, axis=1) # Find which horizontal rows contain at least one text pixel
    cols = np.any(text_mask, axis=0) # Find which vertical columns contain at least one text pixel
    if np.any(rows) and np.any(cols): # Check if any rows and columns have text at all
        rmin, rmax = np.where(rows)[0][[0, -1]] # Get the top-most and bottom-most row indexes containing text
        cmin, cmax = np.where(cols)[0][[0, -1]] # Get the left-most and right-most column indexes containing text
        text_bbox_area = max(1, (rmax - rmin)) * max(1, (cmax - cmin)) # Calculate the rectangular area of the rendered text block
    else: # Fallback if somehow there are no valid rows/columns
        text_bbox_area = 0 # Set the text area to 0

    bubble_area = max(1, by1 - by0) * max(1, bx1 - bx0) # Calculate the total area of the original bounding box
    whitespace_ratio = max(0.0, 1.0 - (text_bbox_area / bubble_area)) # Calculate how much space is left over as a percentage (1 - text_area/bubble_area)

    return float(overflow_rate), float(overlap_rate), float(whitespace_ratio) # Return the three calculated layout metrics

# --------------------------------------------------------- # Visual separator
# OCR AND API CALLS # Section header for API functions
# --------------------------------------------------------- # Visual separator
def run_ocr_for_pil_image(image, upload_name, ocr_api_url): # Define function to send an image to the OCR server
    debug_log("OCR", f"Uploading image: {upload_name}") # Log that the upload has started
    headers = {"ngrok-skip-browser-warning": "true", "Connection": "close"} # Set HTTP headers, bypassing ngrok warnings and closing connections cleanly

    buffer = io.BytesIO() # Create an in-memory byte buffer to hold the image data
    image.save(buffer, format="JPEG", quality=DEFAULT_OCR_JPEG_QUALITY) # Save the PIL image into the buffer as a compressed JPEG
    files_payload = buffer.getvalue() # Extract the raw byte data from the buffer

    last_error = None # Initialize a variable to hold any errors that occur during the request
    for attempt in range(DEFAULT_OCR_RETRIES + 1): # Loop up to max retries + 1 (initial attempt)
        buffer = io.BytesIO(files_payload) # Create a fresh buffer from the raw bytes for this specific attempt
        files = {"file": (f"{upload_name}.jpg", buffer, "image/jpeg")} # Format the payload as a multipart form data file upload
        try: # Start a try block to catch network errors
            response = requests.post( # Make the HTTP POST request
                ocr_api_url,  # To the specified OCR endpoint URL
                files=files,  # Attaching the image payload
                headers=headers,  # Attaching the HTTP headers
                timeout=(DEFAULT_OCR_CONNECT_TIMEOUT_SEC, DEFAULT_OCR_READ_TIMEOUT_SEC) # Applying connection and read timeouts
            ) # End of the POST request arguments
            response.raise_for_status() # Throw an exception if the HTTP status code is an error (e.g., 404, 500)
            data = response.json() # Parse the successful response into a Python dictionary
            break # Break out of the retry loop since the request was successful
        except requests.exceptions.RequestException as exc: # Catch network or timeout errors
            last_error = exc # Save the error for later reference
            time.sleep(min(5, attempt + 1)) # Wait briefly before retrying, increasing the wait time slightly each attempt
    else: # This else executes only if the loop finishes without hitting a 'break' (all retries failed)
        raise TimeoutError("OCR request failed after retries.") from last_error # Raise a fatal error and stop execution

    return data # Return the parsed OCR JSON data

def run_translation(sentences, translation_api_url): # Define a function to translate a list of Japanese sentences
    debug_log("TRANSLATE", f"Translating {len(sentences)} sentence(s)") # Log the number of sentences being translated
    headers = {"ngrok-skip-browser-warning": "true"} # Set headers to bypass ngrok warnings
    translated = [] # Initialize an empty list to store the final Thai translations

    for sentence in sentences: # Loop through each Japanese sentence one by one
        response = requests.post(translation_api_url, json={"japanese_text": sentence}, headers=headers, timeout=120) # POST the text to the translation API with a 120s timeout
        response.raise_for_status() # Throw an error if the translation server fails
        translated.append(response.json().get("translated_text", "")) # Extract the translated string and add it to our list
    return translated # Return the complete list of translated sentences

# --------------------------------------------------------- # Visual separator
# TEXT FORMATTING & RENDERING # Section header for drawing text
# --------------------------------------------------------- # Visual separator
def load_font(font_path, size): # Define function to load a TrueType font
    try: # Start a try block in case the font file is missing
        return ImageFont.truetype(font_path, size) # Load and return the font at the requested size
    except OSError: # Catch the specific error raised if the font file is not found
        return ImageFont.load_default() # Return Pillow's built-in default font as a fallback

def text_size(draw, text, font): # Define a helper to measure text width/height
    box = draw.textbbox((0, 0), text, font=font) # Use the draw object to calculate the exact bounding box of the string
    return box[2] - box[0], box[3] - box[1] # Return the width (xmax-xmin) and height (ymax-ymin)

def compute_line_metrics(draw, font, line_spacing=0, tone_mark_scale=1.0): # Define function to calculate line heights
    _, base_line_h = text_size(draw, "Ag", font) # Measure the height of standard tall/hanging characters ("Ag")
    base_line_h = max(1, base_line_h) # Ensure the height is at least 1 pixel to prevent division by zero later
    rendered_line_h = max(1, int(round(base_line_h * max(0.5, tone_mark_scale)))) # Calculate the final height after applying vertical compression
    return rendered_line_h, max(1, rendered_line_h + int(line_spacing)) # Return the text height and the total line step (height + padding)

def wrap_text_for_box(draw, text, font, max_width): # Define function to wrap text into multiple lines
    if not text: return [] # Return an empty list if there is no text to wrap
    try: # Start try block to attempt loading the Thai NLP library
        from pythainlp import word_tokenize # Import PyThaiNLP specifically for intelligent Thai word tokenization
        words = word_tokenize(text, engine="newmm") # Tokenize the text into logical Thai words
    except ImportError: # Catch error if PyThaiNLP is not installed
        words = text.split() or [text] # Fallback to splitting by simple spaces

    lines, current = [], "" # Initialize the list of lines and the current line string
    for word in words: # Loop through every word
        if font.getlength(current + word) <= max_width: # Check if adding the word exceeds the maximum bubble width
            current += word # If it fits, add it to the current line
        else: # If it does not fit...
            if current: lines.append(current) # Push the completed current line to the list
            current = word # Start a new line with the word that didn't fit
    if current: lines.append(current) # After the loop, push whatever text is left in 'current'
    return lines # Return the list of formatted, wrapped lines

def fit_and_wrap_text(draw, text, font_path, max_width, max_height, start_size=48, min_size=14, line_spacing=0, tone_mark_scale=1.0): # Define function to find the perfect font size
    size = max(min_size, start_size) # Set the starting size, ensuring it's not below our minimum
    while size > min_size: # Loop downwards, shrinking the font size by 1 each time
        font = load_font(font_path, size) # Load the font at the current experimental size
        line_h, line_step = compute_line_metrics(draw, font, line_spacing, tone_mark_scale) # Get the vertical metrics for this size
        lines = wrap_text_for_box(draw, text, font, max_width) # Attempt to wrap the text using this font size
        total_h = line_h + (max(1, len(lines)) - 1) * line_step # Calculate the total height of all wrapped lines combined
        too_wide = any(text_size(draw, ln, font)[0] > max_width for ln in lines if ln) # Check if any single long word violates the width constraint

        if lines and not too_wide and total_h <= max_height: # If we have text, it fits horizontally, AND it fits vertically:
            final_size = max(min_size, size - 6) # Subtract 6 as a safety margin so the text doesn't touch the absolute edge
            if final_size != size: # If the safety margin changed the size...
                font = load_font(font_path, final_size) # Reload the font at the smaller safety size
                line_h, line_step = compute_line_metrics(draw, font, line_spacing, tone_mark_scale) # Recompute line metrics
                lines = wrap_text_for_box(draw, text, font, max_width) # Rewrap the text for the final smaller size
            return font, lines, line_h, line_step # We found the winner! Return the setup
        size -= 1 # If it didn't fit, shrink the font by 1 and try again

    font = load_font(font_path, min_size) # If the loop finishes without fitting, force it to use the minimum size
    line_h, line_step = compute_line_metrics(draw, font, line_spacing, tone_mark_scale) # Get metrics for the minimum size
    return font, wrap_text_for_box(draw, text, font, max_width), line_h, line_step # Return the fallback setup

def draw_scaled_text_line(image, position, text, font, fill="black", y_scale=1.0, text_mask_img=None): # Define function to draw text with vertical squishing
    x, y = position # Unpack the target x,y drawing coordinates
    if y_scale >= 0.99: # Check if we even need to squish it
        ImageDraw.Draw(image).text((x, y), text, fill=fill, font=font) # Just draw it normally on the image
        # Simultaneously draw to the mask array for metric tracking # Comment explaining the mask logic
        if text_mask_img: # Check if a mask image was provided
            ImageDraw.Draw(text_mask_img).text((x, y), text, fill="white", font=font) # Draw the text onto the mask as pure white
        return # Exit early

    temp = Image.new("RGBA", image.size, (0, 0, 0, 0)) # Create a transparent temporary canvas the same size as the image
    temp_draw = ImageDraw.Draw(temp) # Create a drawing context for the temporary canvas
    temp_draw.text((x, y), text, fill=fill, font=font) # Draw the text normally onto the temporary canvas
    box = temp_draw.textbbox((x, y), text, font=font) # Get the bounding box of where the text was drawn
    if not box: return # If the box is empty (no text), exit

    crop = temp.crop(box) # Crop out exactly just the text from the temporary canvas
    new_h = max(1, int(round(crop.height * max(0.5, y_scale)))) # Calculate the new target squished height
    if new_h != crop.height: # Check if squishing is actually required
        crop = crop.resize((crop.width, new_h), Image.Resampling.BICUBIC) # Resize the cropped text using Bicubic filtering for smoothness

    paste_x, paste_y = box[0], box[3] - new_h # Calculate exactly where to paste it back so it aligns with the baseline
    image.paste(crop, (paste_x, paste_y), crop) # Paste the squished text back onto the main image using itself as an alpha mask

    if text_mask_img: # Check if a mask image was provided for metric evaluation
        # Paste the alpha channel of the text crop to generate the boolean mask # Comment explaining alpha extraction
        alpha = crop.split()[3] # Split the RGBA channels and grab the 4th (Alpha/Transparency channel)
        text_mask_img.paste(alpha, (paste_x, paste_y), alpha) # Paste the mask data onto the evaluation canvas

def is_dark_box(image, box, threshold=70): # Define function to check if the background inside a bubble is black
    x0, y0, x1, y1 = box # Unpack the coordinates
    if x1 <= x0 or y1 <= y0: return False # Return False if the box is invalid/negative area
    crop = image.crop((x0, y0, x1 + 1, y1 + 1)).convert("L") # Crop the box region from the image and convert it to grayscale
    return ImageStat.Stat(crop).mean[0] < threshold # Calculate the average brightness and return True if it's below the threshold

def draw_translated_text_in_boxes(image, original_image, ocr_blocks, translated_texts, font_path, padding=8): # Define the master layout engine
    draw = ImageDraw.Draw(image) # Create a drawing context for the main image
    w, h = image.size # Get the width and height of the image
    metrics_report = [] # Initialize a list to hold the metrics for every bubble processed

    for block, translated in zip(ocr_blocks, translated_texts): # Iterate through paired OCR data and Thai translations
        box = block.get("bbox_2d") # Get the bounding box from the OCR block
        if not box or len(box) != 4: continue # Skip if the box is missing or corrupted

        # Keep a pure mask to track text placement for the layout metrics # Comment explaining tracking
        text_mask_img = Image.new("L", image.size, 0) # Create a solid black image to act as our measurement mask

        x0, y0, x1, y1 = [int(v) for v in box] # Convert box coordinates to integers
        top_padding = max(0, int(round(padding * TOP_PADDING_RATIO))) # Calculate reduced top padding
        
        px0 = max(0, x0 - padding) # Apply left padding
        py0 = max(0, y0 - top_padding) # Apply top padding
        px1 = min(w - 1, x1 + padding + RIGHT_PADDING_EXTRA_PX) # Apply right padding + extra safety margin
        py1 = min(h - 1, y1 + padding + 3) # Apply bottom padding

        box_w, box_h = px1 - px0, py1 - py0 # Calculate the width and height of the new padded box
        if box_w <= 0 or box_h <= 0: continue # Skip if the box size is invalid

        dark_box = is_dark_box(original_image, (px0, py0, px1, py1)) # Check if the bubble is black or white based on the unedited original image
        bg_fill = "black" if dark_box else "white" # Set the eraser paint color based on the dark mode check
        text_fill = "white" if dark_box else "black" # Set the text color to contrast with the background
        draw.rectangle([px0, py0, px1, py1], fill=bg_fill) # Erase the Japanese text by painting over the box

        start_size = max(14, int(box_h * 0.8)) # Guess an initial font size based on the height of the bubble
        font, lines, line_h, line_step = fit_and_wrap_text( # Execute the layout algorithm to find the best font size
            draw, translated, font_path, box_w, box_h,  # Pass the context, text, font, and dimensions
            start_size=start_size, line_spacing=LINE_SPACING_PX, tone_mark_scale=TONE_MARK_VERTICAL_SCALE # Pass styling variables
        ) # Close the fit_and_wrap_text call

        if not lines: continue # Skip if the algorithm failed to produce any lines

        total_text_h = line_h + (len(lines) - 1) * line_step # Calculate the total vertical space the text block will consume
        start_y = py0 + max(0, (box_h - total_text_h) // 2) # Calculate the starting Y coordinate to vertically center the block

        y = start_y # Initialize our running Y coordinate
        for line in lines: # Loop through each wrapped line of text
            line_w, _ = text_size(draw, line, font) # Measure the width of this specific line
            line_x = px0 + max(0, (box_w - line_w) // 2) # Calculate the X coordinate to horizontally center this line
            
            draw_scaled_text_line( # Actually draw the text line
                image, (line_x, y), line, font=font, fill=text_fill,  # Pass target, position, text, font, and color
                y_scale=TONE_MARK_VERTICAL_SCALE, text_mask_img=text_mask_img # Pass squish scale and the metrics tracking canvas
            ) # Close the drawing function call
            y += line_step # Move the Y coordinate down for the next line

        # Calculate metrics for this specific text box # Comment explaining evaluation
        overflow, overlap, whitespace = compute_layout_metrics(original_image, text_mask_img, box) # Pass the data to the evaluation logic
        metrics_report.append({ # Append a new dictionary to the report
            "original_text": block.get("text", ""), # Save the original Japanese
            "translated_text": translated, # Save the Thai translation
            "bbox_2d": box, # Save the original coordinates
            "overflow_rate": round(overflow, 4), # Save the overflow score rounded to 4 decimals
            "overlap_rate": round(overlap, 4), # Save the overlap score rounded to 4 decimals
            "whitespace_ratio": round(whitespace, 4) # Save the whitespace score rounded to 4 decimals
        }) # Close the dictionary append

    return image, metrics_report # Return the fully rendered image and the list of collected metrics

# --------------------------------------------------------- # Visual separator
# STANDALONE EXECUTION PIPELINE # Section header for the main execution logic
# --------------------------------------------------------- # Visual separator
def process_single_file(file_path, ocr_api_url, translation_api_url, output_dir, csv_writer): # Define the pipeline for a single file
    debug_log("PIPELINE", f"Start processing: {file_path}") # Log the start of processing
    base_name = Path(file_path).stem # Extract the filename without the extension

    with Image.open(file_path) as src_img: # Open the image file safely
        img = src_img.convert("RGB") # Convert the image to standard RGB format
    
    # Store a pristine copy of the image to reference for background variance and boundaries # Comment explaining original storage
    original_img = img.copy() # Make a deep copy to preserve the original pixels

    ocr_response = run_ocr_for_pil_image(img, upload_name=base_name, ocr_api_url=ocr_api_url) # Call the OCR API
    page_result = (ocr_response.get("results") or [{}])[0] # Safely extract the first result block from the JSON
    blocks = page_result.get("data", {}).get("ocr_blocks", []) # Extract the list of OCR bounding boxes
    valid_blocks = [b for b in blocks if (b.get("text") or "").strip()] # Filter out empty or whitespace-only detections
    
    source_texts = [(b.get("text") or "").strip() for b in valid_blocks] # Extract just the raw strings into a flat list
    translated_texts = run_translation(source_texts, translation_api_url) if source_texts else [] # Call translation API if texts exist

    rendered, layout_metrics = draw_translated_text_in_boxes( # Call the layout and rendering engine
        img, original_img, valid_blocks, translated_texts, DEFAULT_FONT_PATH # Pass all required data and configurations
    ) # Close the call

    out_path = os.path.join(output_dir, f"{base_name}_translated.jpg") # Generate the output filepath
    rendered.save(out_path) # Save the translated, rendered image to disk
    
    # Write metrics to CSV # Comment explaining the writing step
    for metric in layout_metrics: # Loop over every metric dictionary returned by the layout engine
        csv_writer.writerow([ # Write a new row to the open CSV file
            file_path, # Column 1: The path to the file being processed
            metric["bbox_2d"], # Column 2: The original bounding box coordinates
            metric["original_text"], # Column 3: The Japanese text
            metric["translated_text"], # Column 4: The translated text
            metric["overflow_rate"], # Column 5: The overflow metric score
            metric["overlap_rate"], # Column 6: The overlap metric score
            metric["whitespace_ratio"] # Column 7: The whitespace metric score
        ]) # Close the writerow call

    debug_log("PIPELINE", f"Finished processing: {file_path}") # Log that the file is complete

def main(): # Define the main execution block
    # Setup your hardcoded execution variables here # Comment explaining configuration
    INPUT_DIR = "images_to_evaluate" # Set the folder name where your raw manga images are stored
    OUTPUT_DIR = "evaluation_output" # Set the folder name where the translated images should be saved
    OCR_API_URL = "https://d5e7-34-48-243-100.ngrok-free.app/predict" # Set the complete URL to your OCR endpoint
    TRANSLATION_API_URL = "https://0a60-104-197-114-155.ngrok-free.app/translate" # Set the complete URL to your Translation endpoint
    CSV_REPORT_PATH = "rendering_metrics_report.csv" # Set the filename for the final CSV metrics report

    os.makedirs(OUTPUT_DIR, exist_ok=True) # Create the output directory if it doesn't already exist
    images_to_process = collect_input_files([INPUT_DIR]) # Scan the input folder and compile a list of files to process

    if not images_to_process: # Check if the directory was empty
        print(f"No valid images found in {INPUT_DIR}.") # Print a warning to the console
        return # Exit the program

    print(f"Starting batch evaluation on {len(images_to_process)} files...") # Print status to console
    
    with open(CSV_REPORT_PATH, mode='w', newline='', encoding='utf-8') as csv_file: # Open the CSV file safely for writing
        writer = csv.writer(csv_file) # Initialize the CSV writer object
        # CSV Headers including your new Layout Evaluation metrics # Comment explaining headers
        writer.writerow([ # Write the very first row
            "File Path", "Original BBox", "Source Text", "Translated Text",  # Define standard columns
            "Overflow Rate", "Overlap Rate", "Whitespace Ratio" # Define metric columns
        ]) # Close header row

        for file_path in images_to_process: # Loop over every file we found in the input folder
            try: # Start a try block so one bad file doesn't crash the whole batch
                process_single_file(file_path, OCR_API_URL, TRANSLATION_API_URL, OUTPUT_DIR, writer) # Process the file and pass the writer
            except Exception as e: # Catch any error that occurs during processing
                print(f"Failed processing {file_path}: {e}") # Print the error to the console and continue to the next file

    print(f"\nEvaluation Complete! Results saved to: {CSV_REPORT_PATH}") # Print final success message

if __name__ == "__main__": # Standard Python idiom to check if the script is being run directly
    main() # Execute the main function