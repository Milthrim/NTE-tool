"""Screen-only recognition for 甜蜜大摆圈. Coordinates use a 1536 x 864 reference."""
from dataclasses import dataclass
from pathlib import Path
import sys
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'vendor'))
try:
    import cv2
    cv2.setNumThreads(1)
except ImportError:
    cv2 = None

def components(mask, opening=0):
    if cv2 is None:
        if opening:
            mask = ndi.binary_opening(mask, iterations=opening)
        lab, _ = ndi.label(mask)
        return lab, [(i+1, b) for i, b in enumerate(ndi.find_objects(lab)) if b is not None]
    data = np.ascontiguousarray(mask, dtype=np.uint8)
    if opening:
        data = cv2.morphologyEx(data, cv2.MORPH_OPEN,
                               cv2.getStructuringElement(cv2.MORPH_CROSS, (3,3)), iterations=opening)
    count, lab, stats, _ = cv2.connectedComponentsWithStats(data, connectivity=4)
    boxes = [(i, (slice(int(y),int(y+h)),slice(int(x),int(x+w))))
             for i, (x,y,w,h,area) in enumerate(stats) if i and area > 10]
    return lab, boxes

def normalized(mask):
    return np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).resize(
        (32, 32), Image.Resampling.BILINEAR)) > 100

def similarity(a, b):
    return float(np.logical_and(a, b).sum() / max(1, np.logical_or(a, b).sum()))

@dataclass
class Note:
    key: str
    kind: str
    confidence: float
    x: float
    y: float
    width: float
    height: float

    @property
    def size(self):
        return max(self.width, self.height)

@dataclass
class Reading:
    playing: bool = False
    score: int | None = None
    score_text: str = "—"
    reached: bool = False
    button: str | None = None
    note: Note | None = None

class Vision:
    def __init__(self):
        with np.load(ROOT / "assets.npz", allow_pickle=False) as assets:
            self.assets = {k: assets[k].copy() for k in assets.files}
        self.digits = {k[-1]: v for k, v in self.assets.items() if k.startswith("digit_")}
        self.arrows = [(k[-1], v) for k, v in self.assets.items() if k.startswith("arrow_")]

    @staticmethod
    def reference(image):
        if not isinstance(image, Image.Image):
            image = Image.fromarray(image)
        if cv2 is not None:
            a = np.asarray(image if image.mode == 'RGB' else image.convert('RGB'))
            return cv2.resize(a, (1536,864), interpolation=cv2.INTER_AREA) if a.shape[:2] != (864,1536) else a
        if image.size != (1536, 864):
            image = image.resize((1536, 864), Image.Resampling.BILINEAR)
        return np.asarray(image if image.mode == 'RGB' else image.convert("RGB"))

    def patch_match(self, a, name, box, light):
        x, y, x2, y2 = box
        patch = a[y:y2, x:x2]
        mask = patch.min(2) > 205 if light else patch.max(2) < 125
        return similarity(mask, self.assets[name])

    def read_score(self, a):
        r = a[158:196, 1250:1470].astype(np.int16)
        mask = ((r[:, :, 0] > 205) & (r[:, :, 1] > 145) &
                (r[:, :, 2] < 160) & (r[:, :, 0] - r[:, :, 2] > 70))
        lab, _ = ndi.label(mask)
        parts = []
        for i, box in enumerate(ndi.find_objects(lab)):
            if box is None:
                continue
            h = box[0].stop - box[0].start
            w = box[1].stop - box[1].start
            if 17 <= h <= 26 and 6 <= w <= 29 and 6 <= box[0].start <= 12:
                parts.append((box[1].start, box[1].stop, normalized(lab[box] == i + 1)))
        parts.sort(key=lambda x: x[0])
        if not 1 <= len(parts) <= 5:
            return None, "—", False
        if abs((parts[0][0] + parts[-1][1]) / 2 - 110) > 16:
            return None, "—", False
        if any(parts[i + 1][0] - parts[i][1] > 18 for i in range(len(parts) - 1)):
            return None, "—", False
        chars, confidences = [], []
        for _, _, glyph in parts:
            matches = sorted(((max(similarity(glyph, t) for t in ts), d)
                              for d, ts in self.digits.items()), reverse=True)
            quality, digit = matches[0]
            margin = quality - matches[1][0]
            chars.append(digit if quality >= .67 and margin >= .025 else "?")
            confidences.append((quality, margin))
        text = "".join(chars)
        value = int(text) if text.isdigit() else None
        # A reliable leading 9 with four glyphs is enough for this fixed 9000 target.
        reached = ((len(chars) == 4 and chars[0] == "9" and confidences[0][0] >= .82
                    and confidences[0][1] >= .08) or
                   (len(chars) == 5 and chars[0] in "12345678" and value is not None
                    and 10000 <= value < 90000))
        return value, text, reached

    def find_note(self, a):
        full = (cv2.resize(a, (768,432), interpolation=cv2.INTER_AREA) if cv2 is not None else
                np.asarray(Image.fromarray(a).resize((768, 432), Image.Resampling.BILINEAR)))
        small = full[42:360, 280:748]
        r, g, b = (small[:, :, i] for i in range(3))
        candidates = []
        # Bright glyphs are separated from their darker colored diamond and thin grid.
        lowest = np.minimum(np.minimum(r, g), b)
        highest = np.maximum(np.maximum(r, g), b)
        middle = r.astype(np.int16) + g.astype(np.int16) + b.astype(np.int16) - lowest - highest
        bright = (highest > 210) & (middle > 170)
        masks = [(bright & (lowest > t), 1 if t == 180 else 2) for t in (140, 180, 210, 232)]
        # Cyan/yellow glyph interiors are translucent. Their lowest RGB channel
        # stays dark, so white-pixel masks alone miss long/repeated notes.
        ri, gi, bi = r.astype(np.int16), g.astype(np.int16), b.astype(np.int16)
        cyan = (bi > 180) & (gi > 135) & (bi - ri > 40) & (gi - ri > 25)
        amber = (ri > 205) & (gi > 130) & (ri - bi > 65) & (gi - bi > 35)
        if np.count_nonzero(cyan) > 350:
            masks += [((g > t) & (b > 180) & (bi - ri > 20), 2) for t in (135, 170, 205)]
        if np.count_nonzero(amber) > 350:
            masks += [((r > 210) & (g > t) & (ri - bi > 40), 2) for t in (140, 180, 215)]
        for mask, opening in masks:
            mask[222:, 300:] = False  # Fixed WASD controls, not approaching notes.
            mask[8:62, 320:] = False
            lab, boxes = components(mask, opening)
            for label_id, box in boxes:
                h, w = box[0].stop - box[0].start, box[1].stop - box[1].start
                if not (18 < w < 145 and 18 < h < 145 and .6 < w / h < 1.65):
                    continue
                blob = lab[box] == label_id
                if not .18 < blob.mean() < .74:
                    continue
                glyph = normalized(blob)
                matches = sorted(((similarity(glyph, t), key) for key, t in self.arrows), reverse=True)
                quality, key = matches[0]
                if quality < .73 or quality - matches[1][0] < .12:
                    continue
                # Verify the color of the diamond behind the glyph, excluding highlights.
                rgb = small[box].astype(np.int16)
                bg = rgb[~blob]
                saturated = bg[(bg.max(1) - bg.min(1) > 65) & (bg.max(1) > 155)]
                if len(saturated) < 15:
                    continue
                cr, cg, cb = np.median(saturated, axis=0)
                actual = "pink" if cr > cg + 30 and cb > cg + 25 else (
                    "blue" if cb > cr + 30 and cg > cr + 20 else (
                    "orange" if cr > cb + 55 and cg > cb + 25 else None))
                if actual is None:
                    continue
                candidates.append(Note(key, actual, quality,
                                       (box[1].start + 280) * 2 + w, (box[0].start + 42) * 2 + h,
                                       w * 2, h * 2))
        if not candidates:
            return None
        # The largest recognizable approaching arrow is the nearest one.
        return max(candidates, key=lambda n: n.size * (.8 + .2 * n.confidence))

    def analyze(self, image):
        a = self.reference(image)
        playing = self.patch_match(a, "score_header", (1314, 124, 1406, 145), True) > .56
        if playing:
            score, text, reached = self.read_score(a)
            return Reading(True, score, text, reached, note=self.find_note(a))
        retry = self.patch_match(a, "retry", (872, 731, 978, 754), False)
        exit_button = self.patch_match(a, "exit", (580, 731, 635, 754), False)
        if retry > .70 and exit_button > .64:
            return Reading(button="retry")
        start = self.patch_match(a, "start", (1105, 770, 1213, 795), False)
        light_bg = float((a[769:797, 1040:1280].min(2) > 155).mean())
        if start > .70 and light_bg > .55:
            return Reading(button="start")
        return Reading()
