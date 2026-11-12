"""Caption engine — groups TTS word timestamps into short punchy caption lines 
and renders them to transparent PNGs with Pillow (no libass/drawtext needed). 
Styles: karaoke — one PNG per word-state; the word being spoken is highlighted 
pop — one PNG per line, faded in by ffmpeg; 'emphasis' substrings highlighted 
""" 
import re 
from pathlib import Path 
from PIL import Image, ImageDraw, ImageFont 
from common import EMOJI_RE, ZH_PUNCT, emoji_font_path, main_font 

WHITE = (255, 255, 255, 255) 
BLACK = (0, 0, 0, 255) 
SHADOW = (0, 0, 0, 150) 

def hex_rgba(h: str): 
    h = h.lstrip("#") 
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255) 

# ---------------------------------------------------------------- grouping 
def group_words(text: str, words: list, lang: str, max_zh_chars=10, max_en_words=4):
    """Align TTS word tokens back onto the original text (which still has 
    punctuation/emoji) and split them into short caption lines. 
    Returns list of lines: {"words": [{"w","t0","t1","hard"}], "text": str} 
    `hard` marks a token followed by sentence punctuation in the source text. 
    """ 
    toks = [] 
    pos = 0 
    lowered = text.lower() 
    for w in words: 
        token = w["w"] 
        idx = lowered.find(token.lower(), pos) 
        if idx < 0: 
            # token not found verbatim (TTS normalization) — keep it, no punct info
            toks.append({**w, "hard": False}) 
            continue 
        end = idx + len(token) 
        rest = text[end:end + 3] 
        nxt = rest.lstrip(" ")[:1] 
        hard = bool(nxt) and nxt in tuple(ZH_PUNCT) 
        toks.append({**w, "hard": hard, "sentence_end": nxt in "。!?!?….;;"}) 
        pos = end 
    
    lines, cur = [], [] 
    def flush(): 
        if cur: 
            lines.append({"words": list(cur), "text": "".join(t["w"] for t in cur) if lang == "zh" else " ".join(t["w"] for t in cur)}) 
            cur.clear() 
    
    if lang == "zh": 
        for t in toks: 
            chars = sum(len(x["w"]) for x in cur) 
            if cur and chars + len(t["w"]) > max_zh_chars: 
                flush() 
            cur.append(t) 
            if t.get("sentence_end") or (t["hard"] and sum(len(x["w"]) for x in cur) >= 4): 
                flush() 
    else: 
        for t in toks: 
            chars = sum(len(x["w"]) + 1 for x in cur) 
            if cur and (len(cur) + 1 > max_en_words or chars + len(t["w"]) > 24): 
                flush() 
            cur.append(t) 
            if t.get("sentence_end") or (t["hard"] and len(cur) >= 2): 
                flush() 
    flush() 
    
    # display windows: line shows slightly early, holds until the next line 
    for i, ln in enumerate(lines): 
        ln["t0"] = max(0.0, ln["words"][0]["t0"] - 0.07) 
        ln["t1"] = lines[i + 1]["words"][0]["t0"] - 0.07 if i + 1 < len(lines) else ln["words"][-1]["t1"] + 0.30 
    return lines 

# ---------------------------------------------------------------- rendering 
class CaptionRenderer: 
    def __init__(self, W, H, lang, highlight="#FFE14D", uppercase=False): 
        self.W, self.H, self.lang = W, H, lang 
        self.highlight = hex_rgba(highlight) 
        self.uppercase = uppercase 
        
        self.size = int(W * 0.082) 
        self.font = ImageFont.truetype(main_font(lang), self.size) 
        
        ep = emoji_font_path() 
        # CORRECCIÓN AQUÍ: Cambiado 160 por 109 para evitar el OSError
        self.emoji_font = ImageFont.truetype(ep, 109) if ep else None 
        
        self.pad = int(W * 0.06) 
        self.line_h = int(self.size * 1.35) 
        self.max_w = W - 2 * self.pad 

    def _measure(self, text): 
        if hasattr(self.font, "getbbox"): 
            bbox = self.font.getbbox(text) 
            return bbox[2] - bbox[0] 
        return self.font.getlength(text) 

    def _wrap(self, words): 
        lines, cur = [], [] 
        for w in words: 
            test = " ".join(cur + [w]) 
            if self._measure(test) <= self.max_w: 
                cur.append(w) 
            else: 
                if cur: lines.append(cur) 
                cur = [w] 
        if cur: lines.append(cur) 
        return lines 

    def render_line(self, text, highlight_word=None, scale=1.0): 
        img = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0)) 
        draw = ImageDraw.Draw(img) 
        
        words = text.split() 
        wrapped = self._wrap(words) 
        
        total_h = len(wrapped) * self.line_h 
        y = self.H - self.pad - total_h 
        
        for line_words in wrapped: 
            line_text = " ".join(line_words) 
            line_w = self._measure(line_text) 
            x = (self.W - line_w) / 2 
            
            for w in line_words: 
                fill = self.highlight if (highlight_word and w.lower() == highlight_word.lower()) else WHITE 
                
                # Sombra 
                draw.text((x + 3, y + 3), w, font=self.font, fill=SHADOW) 
                # Texto principal 
                draw.text((x, y), w, font=self.font, fill=fill) 
                
                x += self._measure(w + " ") 
            y += self.line_h 
            
        return img 

    def render_karaoke(self, line, out_dir, idx): 
        # Implementación simplificada para generar los frames del karaoke 
        out_paths = [] 
        words = line["words"] 
        for i, w in enumerate(words): 
            img = self.render_line(line["text"], highlight_word=w["w"]) 
            p = Path(out_dir) / f"cap_{idx:04d}_{i:02d}.png" 
            img.save(p) 
            out_paths.append((str(p), w["t0"], w["t1"])) 
        return out_paths 
