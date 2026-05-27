"""
model.py — Advanced NLP text matching engine for Lost & Found AI
Hybrid: TF-IDF cosine similarity + Jaccard + keyword boost
"""
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

STOPWORDS = {
    "the","is","at","which","on","and","a","an","in","for","to","of","with",
    "this","that","was","were","it","by","as","from","are","be","been","has",
    "had","have","do","does","did","but","if","or","because","about","into",
    "through","during","before","after","above","below","up","down","out",
    "off","over","under","again","further","then","once","here","there",
    "when","where","why","how","all","any","both","each","few","more","most",
    "other","some","such","no","nor","not","only","own","same","so","than",
    "too","very","can","will","just","should","now","i","my","its","near",
    "found","lost","item","left","saw","see","please","around","area","campus"
}

SYNONYMS = {
    "pen":        ["pen","pens","ballpen","marker","inkpen","gelpen","ballpoint"],
    "pencil":     ["pencil","graphite","eraser"],
    "phone":      ["phone","mobile","cellphone","smartphone","iphone","android","handphone"],
    "laptop":     ["laptop","notebook","computer","macbook","chromebook"],
    "bag":        ["bag","backpack","schoolbag","handbag","satchel","rucksack","tote"],
    "wallet":     ["wallet","purse","billfold","cardholder","moneyclip"],
    "keys":       ["key","keys","keychain","keyring","keyfob"],
    "id":         ["id","card","idcard","identitycard","studentid","passcard"],
    "bottle":     ["bottle","waterbottle","flask","thermos","sipper"],
    "watch":      ["watch","wristwatch","smartwatch","timepiece"],
    "shoes":      ["shoes","footwear","sneakers","sandals","slippers","boots","heels"],
    "book":       ["book","notebook","textbook","diary","journal","notes"],
    "charger":    ["charger","adapter","cable","cord","usb","type-c"],
    "headphones": ["headphones","earphones","earbuds","airpods","headset"],
    "glasses":    ["glasses","spectacles","eyeglasses","sunglasses","goggles"],
    "umbrella":   ["umbrella","brolly","parasol"],
    "helmet":     ["helmet","headgear"],
    "tiffin":     ["tiffin","lunchbox","dabba","foodcontainer"],
    "calculator": ["calculator","calc","scientific"],
    "ring":       ["ring","band","jewellery","jewelry"],
}

SYN_MAP = {}
for k, vs in SYNONYMS.items():
    for v in vs:
        SYN_MAP[v] = k

HIGH_VALUE_ITEMS = {
    "phone","laptop","wallet","keys","id","watch","glasses","headphones","passport"
}

def clean_text(text):
    if not text: return ""
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def remove_stopwords(text):
    return " ".join(w for w in text.split() if w not in STOPWORDS and len(w) > 1)

def normalize_synonyms(text):
    return " ".join(SYN_MAP.get(w, w) for w in text.split())

def preprocess(text):
    try:
        return normalize_synonyms(remove_stopwords(clean_text(text)))
    except:
        return ""

def tfidf_score(t1, t2):
    try:
        p1, p2 = preprocess(t1), preprocess(t2)
        if not p1 or not p2: return 0.0
        vect = TfidfVectorizer(ngram_range=(1,2), min_df=1, sublinear_tf=True)
        mat  = vect.fit_transform([p1, p2])
        return float(cosine_similarity(mat[0:1], mat[1:2])[0][0])
    except:
        return 0.0

def jaccard_score(t1, t2):
    try:
        s1, s2 = set(preprocess(t1).split()), set(preprocess(t2).split())
        if not s1 or not s2: return 0.0
        return len(s1 & s2) / len(s1 | s2)
    except:
        return 0.0

def keyword_boost(t1, t2):
    """Extra weight when high-value item keywords match exactly."""
    p1, p2 = preprocess(t1).split(), preprocess(t2).split()
    for w in HIGH_VALUE_ITEMS:
        if w in p1 and w in p2:
            return 0.15
    return 0.0

def color_match_bonus(t1, t2):
    colors = {"black","white","red","blue","green","yellow","grey","gray",
              "brown","pink","purple","orange","silver","gold"}
    w1 = set(t1.lower().split()) & colors
    w2 = set(t2.lower().split()) & colors
    if w1 and w2 and w1 & w2:
        return 0.10
    return 0.0

def hybrid_score(text1, text2):
    """
    Final hybrid AI score combining:
    - TF-IDF cosine (60%)
    - Jaccard (20%)
    - Keyword boost (15%)
    - Color match bonus (10%)
    Capped at 1.0.
    """
    tf  = tfidf_score(text1, text2)
    jac = jaccard_score(text1, text2)
    kb  = keyword_boost(text1, text2)
    cb  = color_match_bonus(text1, text2)
    raw = (tf * 0.60) + (jac * 0.20) + kb + cb
    return round(min(raw, 1.0), 4)

def find_best_match(input_text, text_list):
    """
    Returns (best_index, best_score) across a list of candidate texts.
    Each candidate is scored independently — no stale global state.
    """
    if not text_list: return 0, 0.0
    scores = [hybrid_score(input_text, t) for t in text_list]
    best_i = int(max(range(len(scores)), key=lambda i: scores[i]))
    return best_i, scores[best_i]

def score_all(input_text, text_list):
    """Returns list of (index, score) sorted by score desc."""
    scored = [(i, hybrid_score(input_text, t)) for i, t in enumerate(text_list)]
    return sorted(scored, key=lambda x: x[1], reverse=True)

if __name__ == "__main__":
    a = "Lost black leather wallet near canteen"
    b = "Found brown purse near food court"
    c = "Lost blue pen library"
    print("A vs B:", hybrid_score(a, b))
    print("A vs C:", hybrid_score(a, c))
