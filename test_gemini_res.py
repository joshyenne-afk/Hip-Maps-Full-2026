import urllib.request, urllib.error
import json, os, re, base64
from PIL import Image

with open('config.js') as f:
    for line in f:
        m = re.search(r'GEMINI_API_KEY\s*=\s*[\"\']([^\"\']+)[\"\']', line)
        if m:
            api_key = m.group(1)
            break

# Create a 4000x4000 dummy image to see what Gemini returns
img = Image.new('RGB', (4000, 4000), color = 'white')
img.save('dummy.png')

with open('dummy.png', 'rb') as f:
    img_b64 = base64.b64encode(f.read()).decode('utf-8')

prompt = "Turn this into a red square"
payload = {
    "contents": [{"parts": [{"inlineData": {"mimeType": "image/png", "data": img_b64}}, {"text": prompt}]}],
    "generationConfig": {"responseModalities": ["IMAGE"]}
}

req = urllib.request.Request(
    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-image-preview:generateContent?key={api_key}",
    data=json.dumps(payload).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)

try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        res = json.loads(resp.read())
        parts = res['candidates'][0]['content']['parts']
        for p in parts:
            if 'inlineData' in p and p['inlineData']['mimeType'].startswith('image/'):
                with open('dummy_out.png', 'wb') as f:
                    f.write(base64.b64decode(p['inlineData']['data']))
                out_img = Image.open('dummy_out.png')
                print(f"Output size: {out_img.size}")
                break
except Exception as e:
    print(e)
