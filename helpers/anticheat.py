from PIL import Image, ImageFilter
from pathlib import Path

def alter(image):
    '''background_img = "grassfield"
    with open(Path.cwd() / "data" / "backgrounds" / f"{background_img}.png", "rb") as f:
        background = Image.open(f).copy()
    background = background.resize((605,605))
    background.paste(image, (65, 65), image)
    return background'''

    #add any image altering code here 
    image = image.filter(ImageFilter.UnsharpMask(radius=2, percent=20, threshold=2))
    return image