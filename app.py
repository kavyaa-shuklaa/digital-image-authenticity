from PIL import Image
from PIL.ExifTags import TAGS
import hashlib
import json
from datetime import datetime
import os


def analyze_image(filename):

    image = Image.open(filename)
    evidence = {}

    with open(filename, "rb") as file:
        file_data = file.read()


    hash_object = hashlib.sha256(file_data)
    file_hash = hash_object.hexdigest()

    curr = datetime.now()

    unique_part = file_hash[:8]

    analysis_id = (
        "IMG-"
        + curr.strftime("%Y%m%d-%H%M%S")
        + "-"
        + unique_part
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

        # Store the actual quantization tables
        quantization_tables = {}

        for table_id, table in image.quantization.items():

            quantization_tables[str(table_id)] = table

        evidence["quantization_tables"] = quantization_tables

    else:

        evidence["quantization_tables_present"] = False
        evidence["quantization_tables"] = None

    return evidence


def compare_images(evidence1, evidence2):

    comparison = {}

    comparison["sha256_same"] = (
        evidence1["sha256"] == evidence2["sha256"]
    )

    comparison["format_same"] = (
        evidence1["image_format"] == evidence2["image_format"]
    )

    comparison["size_same"] = (
        evidence1["image_size"] == evidence2["image_size"]
    )

    comparison["mode_same"] = (
        evidence1["image_mode"] == evidence2["image_mode"]
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
        evidence1["exif"] == evidence2["exif"]
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

            all_evidence[
                evidence["analysis_id"]
            ] = evidence

    

    with open("evidence.json", "w") as file:

        json.dump(
            all_evidence,
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

                "image_1":
                    evidence1["filename"],

                "image_2":
                    evidence2["filename"],

                "comparison":
                    compare_images(
                        evidence1,
                        evidence2
                    )
            }


    with open(
        "comparison.json",
        "w"
    ) as file:

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

    print(
        "Evidence saved to: evidence.json"
    )

    print(
        "Comparisons saved to: comparison.json"
    )