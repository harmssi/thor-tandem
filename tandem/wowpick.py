"""WoW Forever's game-account chooser: the client always marks the first account and ignores accountList, so Tandem
picks the configured one itself. Looks at the top screen (gamescope screenshot) until the chooser is up, then moves the
mark down to the wanted row and accepts. The chooser sits at a fixed place on the 1920x1080 top screen."""
import subprocess, time
from PIL import Image

SHOT = '/tmp/tandem-wowpick.png'
ROW = 20  # pixels between account rows


def chooser_up(im):
    """Blue mark on the first row and, below it, the red "Annehmen" button. The dialog's height (and so its place)
    changes with what the login form shows, so both are searched in a band instead of at fixed pixels."""
    def find(x, ys, ok):
        return next((y for y in ys if ok(*im.getpixel((x, y)))), None)
    blue = find(1000, range(380, 640, 2), lambda r, g, b: b > 150 and r < 80)
    red = find(894, range(560, 860, 2), lambda r, g, b: r > 120 and g < 40 and b < 40)
    return blue is not None and red is not None and red - blue > 120


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
