from PIL import Image, ImageFilter
import numpy as np
from pathlib import Path
import random

images = {}

for background_img in ("grassback", "sky", "shadow"):
    with open(Path.cwd() / "data" / "backgrounds" / f"{background_img}.png", "rb") as f:
        images[background_img] = Image.open(f).copy()

image_width = 800
image_height = 500

def strip_image(pokemon):
    # convert image to array, strip empty rows and columns
    image_data = np.asarray(pokemon)
    image_data_bw = image_data.take(3, axis=2)
    non_empty_columns = np.where(image_data_bw.max(axis=0)>0)[0]
    non_empty_rows = np.where(image_data_bw.max(axis=1)>0)[0]
    cropBox = (min(non_empty_rows), max(non_empty_rows), min(non_empty_columns), max(non_empty_columns))

    image_data_new = image_data[cropBox[0]:cropBox[1]+1, cropBox[2]:cropBox[3]+1 , :]

    new_image = Image.fromarray(image_data_new)

    return (new_image)

def alter(pokemon, species):
    # TODO make this more readable

    background = images["grassback"]
    pokemon = strip_image(pokemon)
    images["shadow"] = images["shadow"].resize((pokemon.size[0], 100))

    b_width, b_height = background.size
    p_width, p_height = pokemon.size
    s_width, s_height = images["shadow"].size

    try:
        left, top = (
            random.randrange(0, b_width - image_width),
            random.randrange(0, b_height - image_height),
        )
        right, bottom = left + image_width, top + image_height
    except ValueError:
        left, top = 0, 0
        right, bottom = b_width, b_height

    background = background.crop((left, top, right, bottom))

    background.paste(
        images["shadow"],
        ((image_width - s_width) // 2, ((image_height - p_height) // 2) + p_height - (s_height*3)//4),
        images["shadow"],
    )
    background.paste(
        pokemon,
        ((image_width - p_width) // 2, (image_height - p_height) // 2),
        pokemon,
    )

    return background
