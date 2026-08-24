from PIL import Image
from PIL.ExifTags import TAGS
from PIL import ImageFilter, ImageChops
from io import BytesIO

import hashlib
import json
import numpy as np
from datetime import datetime
import os


def analyze_image(filename):
    image = Image.open(filename)
    evidence = {}

    with open(filename, "rb") as file:
        file_data = file.read()

    file_hash = hashlib.sha256(file_data).hexdigest()

    curr = datetime.now()
    analysis_id = (
        "IMG-"
        + curr.strftime("%Y%m%d-%H%M%S")
        + "-"
        + file_hash[:8]
    )

    evidence["analysis_id"] = analysis_id
    evidence["analysis_time"] = curr.strftime("%Y-%m-%d %H:%M:%S")
    evidence["sha256"] = file_hash
    evidence["filename"] = filename

    evidence["image_format"] = image.format
    evidence["image_size"] = image.size
    evidence["image_mode"] = image.mode
    evidence["file_size_bytes"] = len(file_data)

    width, height = image.size
    evidence["pixel_count"] = width * height

    exif = image.getexif()
    exif_data = {}

    for tag_id, value in exif.items():
        tag_name = TAGS.get(tag_id, tag_id)
        exif_data[tag_name] = value

    evidence["exif"] = exif_data

    image_info = {}

    for key, value in image.info.items():
        try:
            json.dumps(value)
            image_info[key] = value
        except TypeError:
            image_info[key] = str(value)

    evidence["image_info"] = image_info

    if image.quantization:
        evidence["quantization_tables_present"] = True

        quantization_tables = {}

        for table_id, table in image.quantization.items():
            quantization_tables[str(table_id)] = table

        evidence["quantization_tables"] = quantization_tables
    else:
        evidence["quantization_tables_present"] = False
        evidence["quantization_tables"] = None

    return evidence


def analyze_noise(filename):
    image = Image.open(filename).convert("L")

    blurred = image.filter(
        ImageFilter.GaussianBlur(radius=1)
    )

    image_array = np.array(
        image,
        dtype=np.float32
    )

    blurred_array = np.array(
        blurred,
        dtype=np.float32
    )

    noise = image_array - blurred_array

    return {
        "noise_mean": float(np.mean(noise)),
        "noise_standard_deviation": float(np.std(noise))
    }


def noise_map(filename, block_size=32):
    image = Image.open(filename).convert("L")

    blurred = image.filter(
        ImageFilter.GaussianBlur(radius=1)
    )

    image_array = np.array(
        image,
        dtype=np.float32
    )

    blurred_array = np.array(
        blurred,
        dtype=np.float32
    )

    noise = image_array - blurred_array

    height, width = noise.shape
    results = []

    for y in range(0, height, block_size):
        for x in range(0, width, block_size):

            block = noise[
                y:min(y + block_size, height),
                x:min(x + block_size, width)
            ]

            results.append({
                "x": x,
                "y": y,
                "width": block.shape[1],
                "height": block.shape[0],
                "noise_standard_deviation": float(np.std(block))
            })

    return results


def ela_analysis(filename, quality=90):
    image = Image.open(filename).convert("RGB")

    buffer = BytesIO()

    image.save(
        buffer,
        format="JPEG",
        quality=quality
    )

    buffer.seek(0)

    compressed = Image.open(buffer)

    difference = ImageChops.difference(
        image,
        compressed
    )

    extrema = difference.getextrema()

    max_difference = max(
        channel_max
        for channel_min, channel_max in extrema
    )

    difference_array = np.array(
        difference,
        dtype=np.float32
    )

    return {
        "ela_quality": quality,
        "ela_max_difference": max_difference,
        "ela_mean_difference": float(
            np.mean(difference_array)
        )
    }


def forensic_analysis(filename):
    return {
        "noise_analysis": analyze_noise(filename),
        "spatial_noise_analysis": noise_map(filename),
        "ela_analysis": ela_analysis(filename)
    }


def generate_findings(evidence, forensic):
    findings = []

    if evidence["exif"]:
        findings.append({
            "category": "Metadata",
            "status": "available",
            "title": "EXIF metadata available",
            "explanation": (
                "The image contains EXIF metadata that can "
                "provide information about the image's origin "
                "or processing history."
            )
        })
    else:
        findings.append({
            "category": "Metadata",
            "status": "limited",
            "title": "No EXIF metadata found",
            "explanation": (
                "No EXIF metadata was available in the image. "
                "This can occur naturally when an image has been "
                "exported, resized, shared, or processed."
            )
        })

    noise_std = forensic[
        "noise_analysis"
    ]["noise_standard_deviation"]

    spatial_noise = forensic[
        "spatial_noise_analysis"
    ]

    noise_values = [
        item["noise_standard_deviation"]
        for item in spatial_noise
    ]

    if noise_values:
        noise_min = min(noise_values)
        noise_max = max(noise_values)

        noise_range = noise_max - noise_min

        if noise_min > 0:
            noise_variation_ratio = (
                noise_max / noise_min
            )
        else:
            noise_variation_ratio = 0

        if noise_variation_ratio >= 3:
            noise_status = "review"
            noise_title = "Regional noise variation detected"
            noise_explanation = (
                "Different regions of the image show "
                "substantially different noise characteristics. "
                "This may occur because of localized editing, "
                "recompression, resizing, or other processing."
            )
        else:
            noise_status = "consistent"
            noise_title = "No strong regional noise variation detected"
            noise_explanation = (
                "The measured noise characteristics do not show "
                "a strong regional difference using the current "
                "analysis method."
            )

        findings.append({
            "category": "Noise",
            "status": noise_status,
            "title": noise_title,
            "explanation": noise_explanation,
            "technical_details": {
                "overall_standard_deviation": noise_std,
                "minimum_block_standard_deviation": noise_min,
                "maximum_block_standard_deviation": noise_max,
                "range": noise_range
            }
        })

    ela = forensic["ela_analysis"]

    findings.append({
        "category": "ELA",
        "status": "review",
        "title": "ELA analysis completed",
        "explanation": (
            "Error Level Analysis was performed to examine "
            "differences produced by JPEG recompression. "
            "ELA results should be interpreted together with "
            "other forensic findings and are not proof of "
            "manipulation by themselves."
        ),
        "technical_details": {
            "quality": ela["ela_quality"],
            "maximum_difference": ela["ela_max_difference"],
            "mean_difference": ela["ela_mean_difference"]
        }
    })

    if evidence["quantization_tables_present"]:
        findings.append({
            "category": "Compression",
            "status": "available",
            "title": "JPEG quantization data available",
            "explanation": (
                "JPEG quantization tables were detected and "
                "preserved as part of the technical evidence."
            )
        })
    else:
        findings.append({
            "category": "Compression",
            "status": "not_available",
            "title": "JPEG quantization data unavailable",
            "explanation": (
                "JPEG quantization tables were not available "
                "for this image."
            )
        })

    return findings


def compare_images(evidence1, evidence2):
    comparison = {}

    comparison["sha256_same"] = (
        evidence1["sha256"]
        == evidence2["sha256"]
    )

    comparison["format_same"] = (
        evidence1["image_format"]
        == evidence2["image_format"]
    )

    comparison["size_same"] = (
        evidence1["image_size"]
        == evidence2["image_size"]
    )

    comparison["mode_same"] = (
        evidence1["image_mode"]
        == evidence2["image_mode"]
    )

    comparison["file_size_same"] = (
        evidence1["file_size_bytes"]
        == evidence2["file_size_bytes"]
    )

    comparison["pixel_count_same"] = (
        evidence1["pixel_count"]
        == evidence2["pixel_count"]
    )

    comparison["exif_same"] = (
        evidence1["exif"]
        == evidence2["exif"]
    )

    comparison["quantization_present_same"] = (
        evidence1["quantization_tables_present"]
        == evidence2["quantization_tables_present"]
    )

    comparison["quantization_tables_same"] = (
        evidence1["quantization_tables"]
        == evidence2["quantization_tables"]
    )

    return comparison


image_folder = "images"

all_evidence = {}
all_forensic_results = {}
all_findings = {}

if not os.path.exists(image_folder):
    print("ERROR: The 'images' folder was not found.")

else:
    for filename in os.listdir(image_folder):

        if filename.lower().endswith(
            (".jpg", ".jpeg", ".png")
        ):

            file_path = os.path.join(
                image_folder,
                filename
            )

            print("\nAnalyzing:", filename)

            evidence = analyze_image(file_path)

            analysis_id = evidence["analysis_id"]

            forensic = forensic_analysis(file_path)

            findings = generate_findings(
                evidence,
                forensic
            )

            all_evidence[analysis_id] = evidence
            all_forensic_results[analysis_id] = forensic
            all_findings[analysis_id] = findings

    with open("evidence.json", "w") as file:
        json.dump(
            all_evidence,
            file,
            indent=4
        )

    with open("forensic_results.json", "w") as file:
        json.dump(
            all_forensic_results,
            file,
            indent=4
        )

    with open("findings.json", "w") as file:
        json.dump(
            all_findings,
            file,
            indent=4
        )

    comparison_results = {}

    evidence_items = list(
        all_evidence.items()
    )

    for i in range(len(evidence_items)):

        for j in range(
            i + 1,
            len(evidence_items)
        ):

            id1, evidence1 = evidence_items[i]
            id2, evidence2 = evidence_items[j]

            comparison_key = (
                id1
                + "_vs_"
                + id2
            )

            comparison_results[
                comparison_key
            ] = {
                "image_1": evidence1["filename"],
                "image_2": evidence2["filename"],
                "comparison": compare_images(
                    evidence1,
                    evidence2
                )
            }

    with open("comparison.json", "w") as file:
        json.dump(
            comparison_results,
            file,
            indent=4
        )

    print("\n================================")
    print("ANALYSIS COMPLETE")
    print("================================")

    print(
        "Total images:",
        len(all_evidence)
    )

    print(
        "Total comparisons:",
        len(comparison_results)
    )

    print("\nFiles created:")
    print("evidence.json")
    print("forensic_results.json")
    print("findings.json")
    print("comparison.json")