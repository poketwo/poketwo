from PIL import Image, ImageFilter
from pathlib import Path
import random
import time

images = {}

for background_img in ("grassback", "sky", "shadow"):
    with open(Path.cwd() / "data" / "backgrounds" / f"{background_img}.png", "rb") as f:
        images[background_img] = Image.open(f).copy()

images["shadow"] = images["shadow"].resize((500, 100))

image_width = 800
image_height = 500


def alter(pokemon, species):
    start_time = time.time()

    #TODO make this more readable

    background = images["grassback"]

    b_width, b_height = background.size

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
        ((image_width - 500) // 2, image_height - 110),
        images["shadow"],
    )
    background.paste(
        pokemon,
        ((image_width - pokemon.size[0]) // 2, (image_height - pokemon.size[1]) // 2),
        pokemon,
    )

    #print(f"Pokemon: {species}")
    #print(f"pHash: {imagehash.phash(background)}")
    #print("--- %s seconds ---" % (time.time() - start_time))
    return background

    #add any image altering code here 
    '''image = image.filter(ImageFilter.UnsharpMask(radius=2, percent=random.randint(10,20), threshold=2))
    return image'''
