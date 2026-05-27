"""
image_model.py — Advanced image similarity engine using OpenCV + perceptual hashing.
Multi-method: histogram + ORB features + hash. Returns weighted confidence score.
"""
import os
import numpy as np

try:
    import cv2
    CV2_OK = True
except ImportError:
    CV2_OK = False

try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    PIL_OK = False


def _load_img(path, size=(128, 128)):
    if not os.path.exists(path):
        return None
    img = cv2.imread(path)
    if img is None:
        return None
    return cv2.resize(img, size)


def histogram_similarity(img1, img2):
    """Compare colour histograms — good for colour/tone matching."""
    scores = []
    for ch in range(3):
        h1 = cv2.calcHist([img1], [ch], None, [64], [0, 256])
        h2 = cv2.calcHist([img2], [ch], None, [64], [0, 256])
        cv2.normalize(h1, h1)
        cv2.normalize(h2, h2)
        scores.append(cv2.compareHist(h1, h2, cv2.HISTCMP_CORREL))
    return float(np.mean(scores))


def orb_similarity(img1, img2):
    """ORB feature matching — good for shape/object similarity."""
    try:
        orb = cv2.ORB_create(nfeatures=300)
        g1  = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
        g2  = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
        kp1, des1 = orb.detectAndCompute(g1, None)
        kp2, des2 = orb.detectAndCompute(g2, None)
        if des1 is None or des2 is None or len(des1) < 2 or len(des2) < 2:
            return 0.0
        bf      = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = bf.match(des1, des2)
        if not matches:
            return 0.0
        matches = sorted(matches, key=lambda m: m.distance)
        good    = [m for m in matches if m.distance < 60]
        return min(len(good) / max(len(kp1), len(kp2), 1), 1.0)
    except:
        return 0.0


def perceptual_hash_similarity(path1, path2):
    """Perceptual hash — good for near-duplicate detection."""
    if not PIL_OK:
        return 0.0
    try:
        def phash(p):
            img = Image.open(p).convert("L").resize((16, 16), Image.LANCZOS)
            arr = np.array(img, dtype=float)
            mean = arr.mean()
            return (arr > mean).flatten()
        h1, h2 = phash(path1), phash(path2)
        diff = np.sum(h1 != h2)
        return 1.0 - diff / 256.0
    except:
        return 0.0


def image_similarity(img1_path, img2_path):
    """
    Weighted multi-method image similarity.
    Returns float [0.0, 1.0]:
      histogram  40%
      ORB        35%
      phash      25%
    Falls back gracefully if OpenCV unavailable.
    """
    if not img1_path or not img2_path:
        return 0.0
    if not os.path.exists(img1_path) or not os.path.exists(img2_path):
        return 0.0

    if not CV2_OK:
        # Pillow-only fallback: phash
        return perceptual_hash_similarity(img1_path, img2_path)

    try:
        i1 = _load_img(img1_path)
        i2 = _load_img(img2_path)
        if i1 is None or i2 is None:
            return 0.0

        hist = max(0.0, histogram_similarity(i1, i2))
        orb  = max(0.0, orb_similarity(i1, i2))
        ph   = perceptual_hash_similarity(img1_path, img2_path)

        score = (hist * 0.40) + (orb * 0.35) + (ph * 0.25)
        return round(min(max(score, 0.0), 1.0), 4)
    except Exception as e:
        print(f"[image_model] error: {e}")
        return 0.0


def analyze_image(img_path):
    """Return dominant colors and rough category for recommendation."""
    result = {"colors": [], "category": "unknown"}
    if not CV2_OK or not os.path.exists(img_path):
        return result
    try:
        img = cv2.imread(img_path)
        if img is None: return result
        img_small = cv2.resize(img, (50, 50)).reshape(-1, 3)
        from collections import Counter
        color_counts = Counter(map(tuple, img_small.tolist()))
        top = [list(c) for c, _ in color_counts.most_common(3)]
        result["colors"] = top
    except:
        pass
    return result
