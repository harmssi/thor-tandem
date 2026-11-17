"""WoW Forever's game-account chooser: the client always marks the first account and ignores accountList, so Tandem
picks the configured one itself. Looks at the top screen (gamescope screenshot) until the chooser is up, then moves the
mark down to the wanted row and accepts. The chooser sits at a fixed place on the 1920x1080 top screen."""
import subprocess, time
from PIL import Image

SHOT = '/tmp/tandem-wowpick.png'
ROW = 20  # pixels between account rows


def chooser_up(im):
    """Blue mark on the first row and the red "Annehmen" button below the list."""
    r, g, b = im.getpixel((1000, 496)); r2, g2, b2 = im.getpixel((894, 664))
    return b > 150 and r < 80 and r2 > 120 and g2 < 40


def pick(index, press, env, timeout=480):
    """index = row of the wanted account (0 = first). press(code) sends one key to the game. True when chosen."""
    until = time.time() + timeout
    while time.time() < until:
        time.sleep(3)
        try:
            subprocess.run(['gamescopectl', 'screenshot', SHOT], env=env, timeout=10, capture_output=True)
            time.sleep(1)
            im = Image.open(SHOT).convert('RGB')
        except Exception: continue
        if im.size == (1920, 1080) and chooser_up(im):
            for _ in range(index): press(108); time.sleep(0.4)  # down
            press(28)  # enter = Annehmen
            return True
    return False
