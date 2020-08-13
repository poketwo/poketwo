from PIL import Image, ImageFilter
from pathlib import Path
import imagehash
import random
import time

def alter(pokemon, species):
    start_time = time.time()

    #TODO make this more readable

    background_img = "grassback"
    with open(Path.cwd() / "data" / "backgrounds" / f"{background_img}.png", "rb") as f:
        background = Image.open(f).copy()
    
    with open(Path.cwd() / "data" / "backgrounds" / f"shadow.png", "rb") as f:
        shadow = Image.open(f).copy()
        shadow = shadow.resize((500, 100))
    
    b_width, b_height = background.size

    image_width = 800
    image_height = 500

    try:
        left, top = random.randrange(0, b_width - image_width), random.randrange(0, b_height - image_height)
        right, bottom = left + image_width, top + image_height
    except ValueError:
        left, top = 0,0
        right, bottom = b_width, b_height
    
    background = background.crop((left, top, right, bottom))

    background.paste(shadow, ((image_width-500)//2, image_height-110), shadow)
    background.paste(pokemon, ((image_width-pokemon.size[0])//2, (image_height-pokemon.size[1])//2), pokemon)

    #print(f"Pokemon: {species}")
    #print(f"pHash: {imagehash.phash(background)}")
    #print("--- %s seconds ---" % (time.time() - start_time))
    return background

    #add any image altering code here 
    '''image = image.filter(ImageFilter.UnsharpMask(radius=2, percent=random.randint(10,20), threshold=2))
    return image'''
