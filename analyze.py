import re

import cv2
import numpy as np
import pytesseract


def _get_longest_line_width(region_img):
    # Sum along rows to find the row with the line
    row_sum = np.sum(region_img == 0, axis=1)  # 0 = black pixels
    line_row = np.argmax(row_sum)  # row with max black pixels

    # Extract that row and find start/end of line
    line_pixels = np.where(region_img[line_row, :] == 0)[0]
    line_start = line_pixels[0]
    line_end = line_pixels[-1]

    return line_end - line_start + 1


def get_scale_info(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    scale_candidates = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        aspect_ratio = w / h
        if 2 < aspect_ratio < 10 and 30 < h < 200 and w > 50:
            scale_candidates.append((x, y, w, h))

    for x, y, w, h in scale_candidates:
        candidate_img = gray[y:y + h, x:x + w]
        text = pytesseract.image_to_string(candidate_img, config="--psm 7")
        match = re.search(r"(\d+)\s*[uμ]m", text)
        if match:
            scale_value = int(match.group(1))

            pixel_length = _get_longest_line_width(candidate_img)
            um_per_pixel = scale_value / pixel_length

            if 0 < um_per_pixel < 100:
                return um_per_pixel

    raise ValueError("No candidate with readable scale found")