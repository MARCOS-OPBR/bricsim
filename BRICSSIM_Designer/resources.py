import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(BASE_DIR, "icons")


def icon_path(filename):
    return os.path.join(ICON_DIR, filename)
